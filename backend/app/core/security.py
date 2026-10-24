import hashlib
import secrets
from datetime import UTC, datetime, timedelta

import jwt
import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.core.config import get_settings

_ph = PasswordHasher()
# Used to keep login timing equal for unknown users.
_DUMMY_HASH = _ph.hash("dummy-password-for-timing")


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password: str, hashed: str | None) -> bool:
    try:
        return _ph.verify(hashed or _DUMMY_HASH, password) and hashed is not None
    except VerifyMismatchError:
        return False


def validate_password_strength(password: str) -> str | None:
    if len(password) < 10:
        return "Пароль должен быть не короче 10 символов"
    if password.isdigit() or password.isalpha():
        return "Пароль должен содержать буквы и цифры"
    return None


def create_access_token(user_id: int, session_id: int, mfa: bool) -> str:
    s = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "sid": session_id,
        "mfa": mfa,
        "iss": s.jwt_issuer,
        "iat": now,
        "exp": now + timedelta(minutes=s.access_ttl_minutes),
        "typ": "access",
    }
    return jwt.encode(payload, s.jwt_secret, algorithm="HS256")


def decode_access_token(token: str) -> dict:
    s = get_settings()
    data = jwt.decode(token, s.jwt_secret, algorithms=["HS256"], issuer=s.jwt_issuer)
    if data.get("typ") != "access":
        raise jwt.InvalidTokenError("wrong token type")
    return data


def new_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def new_totp_secret() -> str:
    return pyotp.random_base32()


def verify_totp(secret: str, code: str) -> bool:
    return pyotp.TOTP(secret).verify(code, valid_window=1)


def totp_uri(secret: str, account: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=account, issuer_name="One English")


def new_otp_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def mask_phone(phone: str | None) -> str | None:
    """+77011234567 -> +7 701 ••• •• 67"""
    if not phone:
        return phone
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) < 6:
        return "•••"
    return f"+{digits[0]} {digits[1:4]} ••• •• {digits[-2:]}"


def normalize_phone(phone: str) -> str:
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    if len(digits) == 10:
        digits = "7" + digits
    return "+" + digits


def create_purpose_token(user_id: int, purpose: str, minutes: int = 5) -> str:
    s = get_settings()
    now = datetime.now(UTC)
    payload = {"sub": str(user_id), "typ": purpose, "iss": s.jwt_issuer, "iat": now, "exp": now + timedelta(minutes=minutes)}
    return jwt.encode(payload, s.jwt_secret, algorithm="HS256")


def decode_purpose_token(token: str, purpose: str) -> int:
    s = get_settings()
    data = jwt.decode(token, s.jwt_secret, algorithms=["HS256"], issuer=s.jwt_issuer)
    if data.get("typ") != purpose:
        raise jwt.InvalidTokenError("wrong token type")
    return int(data["sub"])
