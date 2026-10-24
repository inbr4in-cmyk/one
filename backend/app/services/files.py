"""File storage behind short-lived signed links. Access control = who gets a link (issued only to authorized viewers).

Dev/test: local disk. Production: same interface on S3-compatible storage (private bucket)."""

import hashlib
import hmac
import os
import secrets
import time

from app.core.config import get_settings

ALLOWED = {
    "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif",
    "application/pdf": ".pdf", "audio/mpeg": ".mp3", "audio/ogg": ".ogg", "audio/webm": ".webm", "audio/mp4": ".m4a",
    "video/mp4": ".mp4", "text/plain": ".txt",
    "application/msword": ".doc", "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.ms-excel": ".xls", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
}
# Magic numbers: the declared type must match the bytes.
MAGIC = {
    "image/jpeg": [b"\xff\xd8\xff"], "image/png": [b"\x89PNG"], "image/gif": [b"GIF8"], "image/webp": [b"RIFF"],
    "application/pdf": [b"%PDF"], "audio/ogg": [b"OggS"], "audio/webm": [b"\x1a\x45\xdf\xa3"], "video/mp4": [b"ftyp"],
    "audio/mp4": [b"ftyp"],
}


def _root() -> str:
    path = get_settings().storage_dir
    os.makedirs(path, exist_ok=True)
    return path


def check(content_type: str, head: bytes, size: int) -> str | None:
    if content_type not in ALLOWED:
        return "Этот тип файла нельзя загрузить"
    if size > get_settings().max_upload_mb * 1024 * 1024:
        return f"Файл больше {get_settings().max_upload_mb} МБ"
    sigs = MAGIC.get(content_type)
    if sigs and not any(s in head[:16] for s in sigs):
        return "Содержимое файла не совпадает с его типом"
    return None


def save(data: bytes, content_type: str) -> str:
    key = secrets.token_urlsafe(24) + ALLOWED[content_type]
    with open(os.path.join(_root(), key), "wb") as f:
        f.write(data)
    return key


def path_of(key: str) -> str | None:
    if "/" in key or "\\" in key or key.startswith("."):
        return None
    p = os.path.join(_root(), key)
    return p if os.path.isfile(p) else None


def _sig(key: str, exp: int) -> str:
    return hmac.new(get_settings().jwt_secret.encode(), f"file:{key}:{exp}".encode(), hashlib.sha256).hexdigest()[:32]


def signed_url(key: str | None, ttl: int = 600) -> str | None:
    if not key:
        return None
    if key.startswith("http"):
        return key
    exp = int(time.time()) + ttl
    return f"/api/files/{key}?exp={exp}&sig={_sig(key, exp)}"


def verify(key: str, exp: int, sig: str) -> bool:
    return exp >= time.time() and hmac.compare_digest(_sig(key, exp), sig)
