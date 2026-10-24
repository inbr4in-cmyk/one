from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit
from app.core.config import get_settings
from app.core.security import create_access_token, new_refresh_token, sha256
from app.models.identity import AuthSession, User

MAX_FAILED = 5
LOCK_MINUTES = 15


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
    user.failed_logins = 0
    user.locked_until = None
    await db.flush()
    await write_audit(db, actor_id=user.id, action="auth.login", entity="user", entity_id=user.id, ip=ip,
                      after={"session": sess.id, "mfa": mfa})
    return create_access_token(user.id, sess.id, mfa), refresh, sess


async def rotate(db: AsyncSession, refresh: str, ip: str) -> tuple[str, str]:
    h = sha256(refresh)
    t = now()
    sess = await db.scalar(select(AuthSession).where(AuthSession.refresh_hash == h))
    if sess is None:
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
    await db.commit()
    return create_access_token(user.id, sess.id, sess.mfa_passed), new


async def revoke(db: AsyncSession, sess: AuthSession, reason: str) -> None:
    if sess.revoked_at is None:
        sess.revoked_at = now()
        sess.revoke_reason = reason


async def revoke_all(db: AsyncSession, user_id: int, reason: str, except_id: int | None = None) -> None:
    q = update(AuthSession).where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
    if except_id is not None:
        q = q.where(AuthSession.id != except_id)
    await db.execute(q.values(revoked_at=now(), revoke_reason=reason))


def check_lock(user: User) -> None:
    if user.locked_until and user.locked_until > now():
        raise HTTPException(status.HTTP_423_LOCKED, "Аккаунт временно заблокирован после неудачных попыток входа")


async def register_failure(db: AsyncSession, user: User, ip: str) -> None:
    user.failed_logins += 1
    if user.failed_logins >= MAX_FAILED:
        user.locked_until = now() + timedelta(minutes=LOCK_MINUTES)
        user.failed_logins = 0
    await write_audit(db, actor_id=user.id, action="auth.failed", entity="user", entity_id=user.id, ip=ip)
    await db.commit()
