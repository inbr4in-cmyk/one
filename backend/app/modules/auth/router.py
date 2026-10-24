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
from app.core.security import (
    create_purpose_token,
    decode_purpose_token,
    hash_password,
    new_otp_code,
    new_totp_secret,
    normalize_phone,
    sha256,
    totp_uri,
    validate_password_strength,
    verify_password,
    verify_totp,
)
from app.models.identity import AuthSession, User, UserKind
from app.modules.auth import service
from app.services.messaging import send_whatsapp_text

router = APIRouter(prefix="/auth", tags=["auth"])
REFRESH_COOKIE = "oe_refresh"


class LoginIn(BaseModel):
    phone: str = Field(min_length=6, max_length=32)
    password: str = Field(min_length=1, max_length=256)


class MfaIn(BaseModel):
    mfa_token: str
    code: str = Field(min_length=6, max_length=6)


class OtpRequestIn(BaseModel):
    phone: str = Field(min_length=6, max_length=32)


class OtpVerifyIn(BaseModel):
    phone: str
    code: str = Field(min_length=6, max_length=6)


class TokenOut(BaseModel):
    access_token: str | None = None
    refresh_token: str | None = None  # returned in the body only for mobile clients
    token_type: str = "bearer"
    mfa_required: bool = False
    mfa_token: str | None = None
    mfa_setup_required: bool = False


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


@router.post("/login", response_model=TokenOut)
async def login(body: LoginIn, request: Request, response: Response, db: DB) -> TokenOut:
    ip = client_ip(request)
    s = get_settings()
    await hit(f"login:ip:{ip}", s.login_rate_per_minute, 60)
    phone = normalize_phone(body.phone)
    await hit(f"login:phone:{phone}", s.login_rate_per_minute, 60)
    user = await db.scalar(select(User).where(User.phone == phone, User.archived_at.is_(None)))
    ok = verify_password(body.password, user.password_hash if user else None)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный телефон или пароль")
    service.check_lock(user)
    if not ok:
        await service.register_failure(db, user, ip)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный телефон или пароль")
    if user.totp_enabled:
        return TokenOut(mfa_required=True, mfa_token=create_purpose_token(user.id, "mfa"))
    access, refresh, _ = await service.open_session(db, user, False, ip, request.headers.get("user-agent"))
    await db.commit()
    return _issue(response, request, access, refresh, user, False)


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
    service.check_lock(user)
    # One TOTP code can be used once.
    used_key = f"totp-used:{user.id}:{body.code}"
    if not verify_totp(user.totp_secret, body.code) or await get_kv().get(used_key):
        await service.register_failure(db, user, ip)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный код")
    await get_kv().set(used_key, "1", 120)
    access, refresh, _ = await service.open_session(db, user, True, ip, request.headers.get("user-agent"))
    await db.commit()
    return _issue(response, request, access, refresh, user, True)


@router.post("/otp/request", status_code=204)
async def otp_request(body: OtpRequestIn, request: Request, db: DB) -> None:
    """Students and parents sign in with a one-time code sent to WhatsApp."""
    ip = client_ip(request)
    s = get_settings()
    phone = normalize_phone(body.phone)
    await hit(f"otp:ip:{ip}", s.otp_rate_per_hour * 4, 3600)
    await hit(f"otp:phone:{phone}", s.otp_rate_per_hour, 3600)
    user = await db.scalar(select(User).where(User.phone == phone, User.archived_at.is_(None)))
    # Same response whether or not the phone exists, so the endpoint can't be used to enumerate users.
    if user is None or not user.is_active or user.kind == UserKind.STAFF:
        return None
    code = new_otp_code()
    await get_kv().set(f"otp:{phone}", f"{sha256(code)}:0", 300)
    await send_whatsapp_text(db, phone, f"One English: код для входа {code}. Никому его не сообщайте.",
                             template_code="otp", to_user_id=user.id, sensitive=True)
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
    code_hash, tries = stored.split(":")
    if int(tries) >= 5:
        await kv.delete(f"otp:{phone}")
        raise fail
    if sha256(body.code) != code_hash:
        await kv.set(f"otp:{phone}", f"{code_hash}:{int(tries) + 1}", 300)
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
    response.delete_cookie(REFRESH_COOKIE, path="/api/auth")


class MeOut(BaseModel):
    id: int
    kind: str
    full_name: str
    phone: str
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


@router.post("/2fa/setup")
async def totp_setup(actor: CurrentActor, db: DB) -> dict:
    u = actor.user
    if u.totp_enabled:
        raise bad_request("Двухфакторная защита уже включена")
    secret = new_totp_secret()
    await get_kv().set(f"totp-setup:{u.id}", secret, 600)
    return {"secret": secret, "uri": totp_uri(secret, u.phone)}


class CodeIn(BaseModel):
    code: str = Field(min_length=6, max_length=6)


@router.post("/2fa/enable", response_model=TokenOut)
async def totp_enable(body: CodeIn, actor: CurrentActor, db: DB, request: Request, response: Response) -> TokenOut:
    secret = await get_kv().get(f"totp-setup:{actor.id}")
    if not secret or not verify_totp(secret, body.code):
        raise bad_request("Неверный код из приложения")
    u = actor.user
    u.totp_secret = secret
    u.totp_enabled = True
    await get_kv().delete(f"totp-setup:{actor.id}")
    # Other sessions were opened without 2FA: end them; this one is upgraded to a fresh MFA session.
    await service.revoke_all(db, u.id, "2fa_enabled")
    await write_audit(db, actor_id=u.id, action="auth.2fa_enabled", entity="user", entity_id=u.id, ip=actor.ip)
    access, refresh, _ = await service.open_session(db, u, True, actor.ip, request.headers.get("user-agent"))
    await db.commit()
    return _issue(response, request, access, refresh, u, True)


class PasswordIn(BaseModel):
    old_password: str
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


@router.delete("/sessions/{session_id}", status_code=204)
async def end_session(session_id: int, actor: CurrentActor, db: DB) -> None:
    sess = await db.get(AuthSession, session_id)
    if sess is None or sess.user_id != actor.id:
        raise not_found("Сессия")
    await service.revoke(db, sess, "user_ended")
    await write_audit(db, actor_id=actor.id, action="auth.session_ended", entity="session", entity_id=session_id, ip=actor.ip)
    await db.commit()
