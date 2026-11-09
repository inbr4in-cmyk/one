import hmac
from datetime import UTC, datetime
from typing import Annotated

import jwt
from fastapi import APIRouter, Body, Cookie, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.audit import write_audit
from app.core.config import get_settings
from app.core.deps import DB, CurrentActor
from app.core.errors import bad_request, not_found
from app.core.kv import get_kv
from app.core.permissions import CATALOG
from app.core.ratelimit import client_ip, hit
from app.core.schemas import In
from app.core.security import (
    create_purpose_token,
    decode_purpose_token,
    hash_password,
    new_otp_code,
    new_totp_secret,
    normalize_phone,
    seal_totp_secret,
    sha256,
    totp_uri,
    validate_password_strength,
    verify_password,
    verify_totp,
)
from app.models.identity import AuthSession, User, UserKind
from app.modules.auth import service
from app.services import meta
from app.services.messaging import send_login_code
from app.services.realtime import sessions_ended

router = APIRouter(prefix="/auth", tags=["auth"])
REFRESH_COOKIE = "oe_refresh"


class LoginIn(In):
    phone: str = Field(min_length=6, max_length=32)
    password: str = Field(min_length=1, max_length=256)


class MfaIn(In):
    mfa_token: str = Field(max_length=2000)
    code: str = Field(min_length=6, max_length=6)


class OtpRequestIn(In):
    phone: str = Field(min_length=6, max_length=32)


class OtpVerifyIn(In):
    phone: str = Field(min_length=6, max_length=32)
    code: str = Field(min_length=6, max_length=6)


class TokenOut(BaseModel):
    access_token: str | None = None
    refresh_token: str | None = None  # returned in the body only for mobile clients
    token_type: str = "bearer"
    mfa_required: bool = False
    mfa_token: str | None = None
    mfa_setup_required: bool = False
    device_token: str | None = None  # mobile only: send back as X-Device-Token on the next logins


def _set_refresh_cookie(resp: Response, token: str) -> None:
    s = get_settings()
    resp.set_cookie(
        REFRESH_COOKIE, token, httponly=True, secure=s.cookie_secure, samesite="strict",
        max_age=s.refresh_ttl_days * 86400, path="/api/auth",
    )


def _issue(resp: Response, request: Request, access: str, refresh: str, user: User, mfa: bool) -> TokenOut:
    mobile = request.headers.get("x-client") == "mobile"
    if not mobile:
        _set_refresh_cookie(resp, refresh)
    s = get_settings()
    return TokenOut(
        access_token=access,
        refresh_token=refresh if mobile else None,
        mfa_setup_required=user.kind == UserKind.STAFF and s.require_staff_2fa and not user.totp_enabled,
    )


def _device(request: Request) -> str | None:
    return request.cookies.get(service.DEVICE_COOKIE) or request.headers.get("x-device-token")


def _remember_device(resp: Response, request: Request, user: User, out: TokenOut) -> TokenOut:
    """A signed «this device signed in before» token: with it a correct password is never held back by failed tries."""
    token = service.device_token(user.id)
    if request.headers.get("x-client") == "mobile":
        out.device_token = token
    else:
        s = get_settings()
        resp.set_cookie(service.DEVICE_COOKIE, token, httponly=True, secure=s.cookie_secure, samesite="strict",
                        max_age=service.DEVICE_DAYS * 86400, path="/api/auth")
    return out


@router.post("/login", response_model=TokenOut)
async def login(body: LoginIn, request: Request, response: Response, db: DB) -> TokenOut:
    """QA B-4: failed passwords slow down the phone + IP they came from (growing pauses), they never lock the account.
    Unknown phones get exactly the same answers, so the endpoint doesn't reveal who has an account."""
    ip = client_ip(request)
    s = get_settings()
    # A hard ceiling before any password hashing (CPU), well above what a real person needs.
    await hit(f"login:ip-hard:{ip}", s.login_rate_per_minute * 6, 60)
    phone = normalize_phone(body.phone)
    user = await db.scalar(select(User).where(User.phone == phone, User.archived_at.is_(None)))
    ok = verify_password(body.password, user.password_hash if user else None)
    if user is not None and not user.is_active:
        user, ok = None, False
    known = user is not None and await service.is_known(db, user, ip, _device(request))
    if not (ok and known):
        # Everything except «right password from a known place» shares per-IP and per-phone budgets, so neither one IP
        # spraying many phones nor many IPs on one phone go fast.
        try:
            await hit(f"login:ip:{ip}", s.login_rate_per_minute, 60)
            await hit(f"login:phone:{phone}", s.login_rate_per_minute, 60)
            if wait := await service.wait_left(phone, ip):
                raise service.too_many(wait)
        except HTTPException:
            await service.record_burst(db, phone, ip, user)
            raise
    if not ok:
        await service.record_failure(db, phone, ip, user)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный телефон или пароль")
    await service.clear_failures(phone, ip)
    if user.totp_enabled:
        return _remember_device(response, request, user,
                                TokenOut(mfa_required=True, mfa_token=create_purpose_token(user.id, "mfa")))
    access, refresh, _ = await service.open_session(db, user, False, ip, request.headers.get("user-agent"))
    await db.commit()
    return _remember_device(response, request, user, _issue(response, request, access, refresh, user, False))


@router.post("/mfa", response_model=TokenOut)
async def mfa(body: MfaIn, request: Request, response: Response, db: DB) -> TokenOut:
    ip = client_ip(request)
    try:
        user_id = decode_purpose_token(body.mfa_token, "mfa")
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Код устарел, войдите заново") from None
    await hit(f"mfa:{user_id}", 5, 300)
    user = await db.get(User, user_id)
    if user is None or not user.totp_enabled or not user.totp_secret:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный код")
    # One TOTP code can be used once.
    used_key = f"totp-used:{user.id}:{body.code}"
    if not verify_totp(user.totp_secret, body.code) or await get_kv().get(used_key):
        await service.record_failure(db, f"mfa:{user.id}", ip, user)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный код")
    await get_kv().set(used_key, "1", 120)
    if not user.totp_secret.startswith("enc1:"):
        user.totp_secret = seal_totp_secret(user.totp_secret)
    access, refresh, _ = await service.open_session(db, user, True, ip, request.headers.get("user-agent"))
    await db.commit()
    return _issue(response, request, access, refresh, user, True)


@router.post("/otp/request", status_code=204)
async def otp_request(body: OtpRequestIn, request: Request, db: DB) -> None:
    """Students and parents sign in with a one-time code sent to WhatsApp."""
    ip = client_ip(request)
    s = get_settings()
    if s.is_prod and not meta.wa_configured():
        # Checked before the phone lookup, so it reveals nothing about who is registered.
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Вход по коду WhatsApp пока не подключён. Обратитесь в школу.")
    phone = normalize_phone(body.phone)
    await hit(f"otp:ip:{ip}", s.otp_rate_per_hour * 4, 3600)
    await hit(f"otp:phone:{phone}", s.otp_rate_per_hour, 3600)
    user = await db.scalar(select(User).where(User.phone == phone, User.archived_at.is_(None)))
    # Same response whether or not the phone exists, so the endpoint can't be used to enumerate users.
    if user is None or not user.is_active or user.kind == UserKind.STAFF:
        return None
    code = new_otp_code()
    await get_kv().set(f"otp:{phone}", sha256(code), 300)
    await get_kv().delete(f"otp-tries:{phone}")
    await send_login_code(db, phone, code, to_user_id=user.id, locale=user.locale or "ru")
    await db.commit()


@router.post("/otp/verify", response_model=TokenOut)
async def otp_verify(body: OtpVerifyIn, request: Request, response: Response, db: DB) -> TokenOut:
    ip = client_ip(request)
    phone = normalize_phone(body.phone)
    kv = get_kv()
    stored = await kv.get(f"otp:{phone}")
    fail = HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный или устаревший код")
    if not stored:
        raise fail
    # Atomic counter: parallel guesses can't share one "try".
    if await kv.incr(f"otp-tries:{phone}", 300) > 5:
        await kv.delete(f"otp:{phone}")
        raise fail
    if not hmac.compare_digest(sha256(body.code), stored):
        raise fail
    await kv.delete(f"otp:{phone}")
    user = await db.scalar(select(User).where(User.phone == phone, User.archived_at.is_(None)))
    if user is None or not user.is_active or user.kind == UserKind.STAFF:
        raise fail
    access, refresh, _ = await service.open_session(db, user, True, ip, request.headers.get("user-agent"))
    await db.commit()
    return _issue(response, request, access, refresh, user, True)


@router.post("/refresh", response_model=TokenOut)
async def refresh(
    request: Request,
    response: Response,
    db: DB,
    oe_refresh: Annotated[str | None, Cookie()] = None,
    body: Annotated[dict | None, Body()] = None,
) -> TokenOut:
    token = oe_refresh or (body or {}).get("refresh_token")
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Сессия истекла")
    # Cookie-based refresh must come from our own frontend (CSRF guard on top of SameSite=Strict).
    if oe_refresh and request.headers.get("x-requested-with") != "one-english":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Недопустимый запрос")
    access, new = await service.rotate(db, token, client_ip(request))
    mobile = request.headers.get("x-client") == "mobile"
    if not mobile:
        _set_refresh_cookie(response, new)
    return TokenOut(access_token=access, refresh_token=new if mobile else None)


@router.post("/logout", status_code=204)
async def logout(actor: CurrentActor, db: DB, response: Response) -> None:
    sess = await db.get(AuthSession, actor.session_id)
    if sess:
        await service.revoke(db, sess, "logout")
    await write_audit(db, actor_id=actor.id, action="auth.logout", entity="session", entity_id=actor.session_id, ip=actor.ip)
    await db.commit()
    await sessions_ended(actor.id, only=[actor.session_id])
    response.delete_cookie(REFRESH_COOKIE, path="/api/auth")


class DeviceIn(In):
    platform: str = Field(pattern="^(ios|android)$")
    token: str = Field(min_length=20, max_length=512)
    locale: str = Field(default="ru", pattern="^(ru|kk)$")


@router.post("/devices", status_code=204)
async def register_device(body: DeviceIn, actor: CurrentActor, db: DB) -> None:
    """The mobile app registers its push token after login; it belongs to this session only."""
    from app.models import DeviceToken

    d = await db.scalar(select(DeviceToken).where(DeviceToken.token == body.token))
    if d is None:
        d = DeviceToken(token=body.token, user_id=actor.id, session_id=actor.session_id, platform=body.platform)
        db.add(d)
    # A phone handed to another person moves with the new login.
    d.user_id, d.session_id, d.platform, d.locale, d.last_seen_at = actor.id, actor.session_id, body.platform, body.locale, datetime.now(UTC)
    await db.commit()


@router.delete("/devices/{token}", status_code=204)
async def unregister_device(token: str, actor: CurrentActor, db: DB) -> None:
    from app.models import DeviceToken

    d = await db.scalar(select(DeviceToken).where(DeviceToken.token == token, DeviceToken.user_id == actor.id))
    if d:
        await db.delete(d)
        await db.commit()


class MeOut(BaseModel):
    id: int
    kind: str
    full_name: str
    phone: str | None
    locale: str
    avatar_url: str | None
    position: str | None
    totp_enabled: bool
    mfa: bool
    roles: list[str]
    branch_ids: list[int]
    permissions: dict[str, str]
    rules_accepted_version: str | None
    mfa_setup_required: bool = False


@router.get("/me", response_model=MeOut)
async def me(actor: CurrentActor) -> MeOut:
    u = actor.user
    return MeOut(
        id=u.id, kind=u.kind, full_name=u.full_name, phone=u.phone, locale=u.locale, avatar_url=u.avatar_url,
        position=u.position, totp_enabled=u.totp_enabled, mfa=actor.mfa, roles=sorted(actor.role_codes),
        branch_ids=sorted(actor.branch_ids),
        permissions={f"{m}.{a}": s for (m, a), s in actor.grants.scopes.items()},
        rules_accepted_version=u.rules_accepted_version,
        mfa_setup_required=actor.is_staff and get_settings().require_staff_2fa and not u.totp_enabled,
    )


@router.get("/catalog")
async def permission_catalog(actor: CurrentActor) -> dict:
    return {m: {"title": t, "actions": acts} for m, (t, acts) in CATALOG.items()}


class TotpSetupIn(In):
    password: str | None = Field(default=None, max_length=256)


@router.post("/2fa/setup")
async def totp_setup(actor: CurrentActor, db: DB, body: TotpSetupIn | None = None) -> dict:
    """QA H-5: a stolen session alone can't attach the thief's authenticator — the password is asked again."""
    u = actor.user
    if u.totp_enabled:
        raise bad_request("Двухфакторная защита уже включена")
    if u.password_hash:
        await hit(f"2fa-setup:{u.id}", 5, 300)
        if not body or not body.password or not verify_password(body.password, u.password_hash):
            raise bad_request("Введите текущий пароль")
    secret = new_totp_secret()
    await get_kv().set(f"totp-setup:{u.id}", secret, 600)
    return {"secret": secret, "uri": totp_uri(secret, u.phone or f"id{u.id}")}


class CodeIn(In):
    code: str = Field(min_length=6, max_length=6)


@router.post("/2fa/enable", response_model=TokenOut)
async def totp_enable(body: CodeIn, actor: CurrentActor, db: DB, request: Request, response: Response) -> TokenOut:
    secret = await get_kv().get(f"totp-setup:{actor.id}")
    if not secret or not verify_totp(secret, body.code):
        raise bad_request("Неверный код из приложения")
    u = actor.user
    u.totp_secret = seal_totp_secret(secret)
    u.totp_enabled = True
    await get_kv().delete(f"totp-setup:{actor.id}")
    # Other sessions were opened without 2FA: end them; this one is upgraded to a fresh MFA session.
    await service.revoke_all(db, u.id, "2fa_enabled")
    await write_audit(db, actor_id=u.id, action="auth.2fa_enabled", entity="user", entity_id=u.id, ip=actor.ip)
    access, refresh, _ = await service.open_session(db, u, True, actor.ip, request.headers.get("user-agent"))
    await db.commit()
    await sessions_ended(u.id)
    return _issue(response, request, access, refresh, u, True)


class PasswordIn(In):
    old_password: str = Field(max_length=256)
    new_password: str = Field(min_length=10, max_length=256)


@router.post("/password", status_code=204)
async def change_password(body: PasswordIn, actor: CurrentActor, db: DB) -> None:
    u = actor.user
    if not verify_password(body.old_password, u.password_hash):
        raise bad_request("Текущий пароль неверный")
    if err := validate_password_strength(body.new_password):
        raise bad_request(err)
    u.password_hash = hash_password(body.new_password)
    await service.revoke_all(db, u.id, "password_changed", except_id=actor.session_id)
    await write_audit(db, actor_id=u.id, action="auth.password_changed", entity="user", entity_id=u.id, ip=actor.ip)
    await db.commit()
    await sessions_ended(u.id, keep=actor.session_id)


class SessionOut(BaseModel):
    id: int
    user_agent: str | None
    ip: str | None
    created_at: datetime
    last_used_at: datetime
    mfa_passed: bool
    current: bool


@router.get("/sessions", response_model=list[SessionOut])
async def my_sessions(actor: CurrentActor, db: DB) -> list[SessionOut]:
    rows = await db.scalars(
        select(AuthSession)
        .where(AuthSession.user_id == actor.id, AuthSession.revoked_at.is_(None), AuthSession.expires_at > datetime.now(UTC))
        .order_by(AuthSession.last_used_at.desc())
    )
    return [
        SessionOut(id=s.id, user_agent=s.user_agent, ip=s.ip, created_at=s.created_at, last_used_at=s.last_used_at,
                   mfa_passed=s.mfa_passed, current=s.id == actor.session_id)
        for s in rows
    ]


@router.delete("/sessions", status_code=204)
async def end_other_sessions(actor: CurrentActor, db: DB) -> None:
    await service.revoke_all(db, actor.id, "user_ended_others", except_id=actor.session_id)
    await write_audit(db, actor_id=actor.id, action="auth.sessions_ended_others", entity="user", entity_id=actor.id, ip=actor.ip)
    await db.commit()
    await sessions_ended(actor.id, keep=actor.session_id)


@router.delete("/sessions/{session_id}", status_code=204)
async def end_session(session_id: int, actor: CurrentActor, db: DB) -> None:
    sess = await db.get(AuthSession, session_id)
    if sess is None or sess.user_id != actor.id:
        raise not_found("Сессия")
    await service.revoke(db, sess, "user_ended")
    await write_audit(db, actor_id=actor.id, action="auth.session_ended", entity="session", entity_id=session_id, ip=actor.ip)
    await db.commit()
    await sessions_ended(actor.id, only=[session_id])
