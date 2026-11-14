import time
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit
from app.core.config import get_settings
from app.core.kv import get_kv
from app.core.security import create_access_token, create_purpose_token, decode_purpose_token, new_refresh_token, sha256
from app.models.identity import AuthSession, Role, User, UserRole
from app.services.messaging import notify_user


REFRESH_GRACE_S = 20


def now() -> datetime:
    return datetime.now(UTC)


async def open_session(db: AsyncSession, user: User, mfa: bool, ip: str, ua: str | None) -> tuple[str, str, AuthSession]:
    s = get_settings()
    refresh = new_refresh_token()
    t = now()
    sess = AuthSession(
        user_id=user.id,
        refresh_hash=sha256(refresh),
        user_agent=(ua or "")[:255],
        ip=ip,
        mfa_passed=mfa,
        created_at=t,
        last_used_at=t,
        expires_at=t + timedelta(days=s.refresh_ttl_days),
    )
    db.add(sess)
    user.last_login_at = t
    await db.flush()
    await write_audit(db, actor_id=user.id, action="auth.login", entity="user", entity_id=user.id, ip=ip,
                      after={"session": sess.id, "mfa": mfa})
    return create_access_token(user.id, sess.id, mfa), refresh, sess


async def rotate(db: AsyncSession, refresh: str, ip: str) -> tuple[str, str]:
    h = sha256(refresh)
    t = now()
    # Row lock: two parallel refreshes with the same token can't both rotate it.
    sess = await db.scalar(select(AuthSession).where(AuthSession.refresh_hash == h).with_for_update())
    if sess is None:
        # QA C-6: two tabs (or a retried request) refreshing with the same token within a few seconds get the
        # pair the first one received, instead of being treated as theft.
        cached = await get_kv().get(f"refresh-grace:{h}")
        if cached:
            sid, access, new = cached.split(" ", 2)
            fresh = await db.get(AuthSession, int(sid), populate_existing=True)
            if fresh is not None and fresh.is_live(t) and fresh.refresh_hash == sha256(new):
                return access, new
        # Reuse of an already-rotated token means it was stolen: revoke that whole session.
        stolen = await db.scalar(select(AuthSession).where(AuthSession.prev_refresh_hash == h))
        if stolen is not None and stolen.revoked_at is None:
            stolen.revoked_at = t
            stolen.revoke_reason = "refresh_reuse"
            await write_audit(db, actor_id=stolen.user_id, action="auth.refresh_reuse", entity="session",
                              entity_id=stolen.id, ip=ip)
            await db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Сессия истекла")
    if not sess.is_live(t):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Сессия истекла")
    user = await db.get(User, sess.user_id)
    if user is None or not user.is_active or user.archived_at is not None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Сессия истекла")
    new = new_refresh_token()
    sess.prev_refresh_hash = h
    sess.refresh_hash = sha256(new)
    sess.last_used_at = t
    sess.ip = ip
    access = create_access_token(user.id, sess.id, sess.mfa_passed)
    await get_kv().set(f"refresh-grace:{h}", f"{sess.id} {access} {new}", REFRESH_GRACE_S)
    await db.commit()
    return access, new


async def revoke(db: AsyncSession, sess: AuthSession, reason: str) -> None:
    if sess.revoked_at is None:
        sess.revoked_at = now()
        sess.revoke_reason = reason


async def revoke_all(db: AsyncSession, user_id: int, reason: str, except_id: int | None = None) -> None:
    q = update(AuthSession).where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
    if except_id is not None:
        q = q.where(AuthSession.id != except_id)
    await db.execute(q.values(revoked_at=now(), revoke_reason=reason))


# ---------- failed logins (QA B-4) ----------
# Failures are counted per phone + IP. After FREE_TRIES the next try from that IP waits 30 s, then 60 s, 120 s…
# up to 15 min. Nobody can lock an account: a correct password from a device or IP the user has signed in from
# before always gets in, and other IPs have their own counters. A burst of failures on one account alerts the owners.
FREE_TRIES = 5
BASE_DELAY_S = 30
MAX_DELAY_S = 15 * 60
COUNTER_TTL = 24 * 3600
BURST = 10  # failures on one phone within an hour, from any IPs
DEVICE_COOKIE = "oe_device"
DEVICE_DAYS = 365


def _fail_key(phone: str, ip: str) -> str:
    return f"login:fail:{phone}:{ip}"


def delay_for(failures: int) -> int:
    if failures < FREE_TRIES:
        return 0
    return min(BASE_DELAY_S * 2 ** (failures - FREE_TRIES), MAX_DELAY_S)


async def wait_left(phone: str, ip: str) -> int:
    """Seconds this phone + IP must still wait before the next password is checked."""
    kv = get_kv()
    raw = await kv.get(_fail_key(phone, ip))
    if not raw:
        return 0
    failures, last = (int(x) for x in raw.split(":"))
    return max(0, last + delay_for(failures) - int(time.time()))


async def record_failure(db: AsyncSession, phone: str, ip: str, user: User | None) -> None:
    kv = get_kv()
    raw = await kv.get(_fail_key(phone, ip))
    failures = int(raw.split(":")[0]) + 1 if raw else 1
    await kv.set(_fail_key(phone, ip), f"{failures}:{int(time.time())}", COUNTER_TTL)
    if user is not None:
        await write_audit(db, actor_id=user.id, action="auth.failed", entity="user", entity_id=user.id, ip=ip,
                          after={"failures_from_ip": failures})
    await record_burst(db, phone, ip, user)


async def record_burst(db: AsyncSession, phone: str, ip: str, user: User | None) -> None:
    """Every rejected try (wrong password or throttled) counts toward the owners' alert."""
    burst = await get_kv().incr(f"login:burst:{phone}", 3600)
    if user is not None and burst == BURST:
        await _alert_owners(db, user, ip)
    await db.commit()


async def clear_failures(phone: str, ip: str) -> None:
    await get_kv().delete(_fail_key(phone, ip))


async def _alert_owners(db: AsyncSession, user: User, ip: str) -> None:
    owners = await db.scalars(select(UserRole.user_id).join(Role, Role.id == UserRole.role_id).join(User, User.id == UserRole.user_id)
                              .where(Role.code == "owner", User.is_active.is_(True), User.archived_at.is_(None)))
    for uid in set(owners):
        await notify_user(db, uid, "security", f"Много неудачных входов: {user.full_name}",
                          body=f"{BURST} неверных паролей за час, последний с IP {ip}", link="/settings/security")


def device_token(user_id: int) -> str:
    return create_purpose_token(user_id, "device", minutes=DEVICE_DAYS * 24 * 60)


async def is_known(db: AsyncSession, user: User, ip: str, device: str | None) -> bool:
    """A device that signed in before (its cookie / X-Device-Token), or an IP this user has had a session from."""
    if device:
        try:
            if decode_purpose_token(device, "device") == user.id:
                return True
        except jwt.PyJWTError:
            pass
    return await db.scalar(select(AuthSession.id).where(
        AuthSession.user_id == user.id, AuthSession.ip == ip, AuthSession.created_at > now() - timedelta(days=180)).limit(1)) is not None


def too_many(wait: int) -> HTTPException:
    return HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, f"Слишком много неверных попыток. Попробуйте через {wait} с",
                         headers={"Retry-After": str(wait)})
