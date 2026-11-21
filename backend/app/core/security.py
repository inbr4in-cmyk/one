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


PASSWORD_MIN = 10
PASSWORD_MAX = 256
# The most common passwords and keyboard walks that pass the length rule (QA C-8). Compared case-insensitively,
# also with trailing digits/punctuation stripped («Qwerty12345!» → «qwerty»).
COMMON_PASSWORDS = frozenset("""
password passw0rd qwerty qwertyuiop qwerty123 qwerty1234 qwertyuiop123 asdfghjkl zxcvbnm 1q2w3e4r5t 1q2w3e4r1q2w3e4r
q1w2e3r4t5 1qaz2wsx3edc qazwsxedc qazwsx zaq12wsx iloveyou letmein welcome admin administrator adminadmin
changeme secret monkey dragon football baseball superman batman princess sunshine starwars master trustno1
abc123 abcdef abcdefgh abcd1234 a1b2c3d4e5 password1 password123 p@ssw0rd p@ssword пароль йцукен йцукенгшщз
oneenglish one-english englishschool english school shymkent kazakhstan almaty astana
""".split())


def _core(password: str) -> str:
    p = password.lower().strip()
    return p.rstrip("0123456789!@#$%^&*()_-+=.?,;:")


def validate_password_strength(password: str) -> str | None:
    if len(password) < PASSWORD_MIN:
        return f"Пароль должен быть не короче {PASSWORD_MIN} символов"
    if len(password) > PASSWORD_MAX:
        return f"Пароль должен быть не длиннее {PASSWORD_MAX} символов"
    if password.isdigit() or password.isalpha():
        return "Пароль должен содержать буквы и цифры"
    low = password.lower()
    if low in COMMON_PASSWORDS or _core(password) in COMMON_PASSWORDS or len(set(low)) < 4:
        return "Этот пароль слишком простой и часто встречается — придумайте другой"
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


_ENC = "enc1:"


def _fernet():
    import base64

    from cryptography.fernet import Fernet

    s = get_settings()
    # OE_TOTP_KEY (Fernet key) when set; otherwise a key derived from OE_JWT_SECRET for this purpose only.
    key = s.totp_key or base64.urlsafe_b64encode(hashlib.sha256(f"totp-secret:{s.jwt_secret}".encode()).digest()).decode()
    return Fernet(key)


def seal_totp_secret(secret: str) -> str:
    """2FA secrets are stored encrypted (QA H-5): a database dump alone can't produce codes."""
    return _ENC + _fernet().encrypt(secret.encode()).decode()


def open_totp_secret(stored: str | None) -> str | None:
    if not stored:
        return None
    if stored.startswith(_ENC):
        return _fernet().decrypt(stored[len(_ENC):].encode()).decode()
    return stored  # stored before encryption was added; re-sealed on the next successful sign-in


def verify_totp(secret: str | None, code: str) -> bool:
    secret = open_totp_secret(secret) if secret and secret.startswith(_ENC) else secret
    return bool(secret) and pyotp.TOTP(secret).verify(code, valid_window=1)


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
