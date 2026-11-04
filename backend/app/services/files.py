"""File storage behind short-lived signed links. Access control = who gets a link (issued only to authorized viewers).

Dev/test: local disk. Production: same interface on S3-compatible storage (private bucket)."""

import hashlib
import hmac
import os
import secrets
import time
from urllib.parse import quote

from app.core.config import get_settings

ALLOWED = {
    "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif",
    "application/pdf": ".pdf", "audio/mpeg": ".mp3", "audio/ogg": ".ogg", "audio/webm": ".webm", "audio/mp4": ".m4a",
    "video/mp4": ".mp4", "text/plain": ".txt",
    "application/msword": ".doc", "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.ms-excel": ".xls", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
}
# Magic numbers: the declared type must match the bytes, checked from byte 0 (QA C-11).
MAGIC: dict[str, list[tuple[int, bytes]]] = {
    "image/jpeg": [(0, b"\xff\xd8\xff")], "image/png": [(0, b"\x89PNG\r\n\x1a\n")], "image/gif": [(0, b"GIF87a"), (0, b"GIF89a")],
    "image/webp": [(0, b"RIFF")], "application/pdf": [(0, b"%PDF-")], "audio/ogg": [(0, b"OggS")],
    "audio/webm": [(0, b"\x1a\x45\xdf\xa3")], "video/mp4": [(4, b"ftyp")], "audio/mp4": [(4, b"ftyp")],
    "audio/mpeg": [(0, b"ID3"), (0, b"\xff\xfb"), (0, b"\xff\xf3"), (0, b"\xff\xf2")],
    "application/msword": [(0, b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")],
    "application/vnd.ms-excel": [(0, b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")],
}
# Office Open XML files are ZIP archives with a known layout.
OOXML = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "word/",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xl/",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "ppt/",
}
MAX_ZIP_ENTRIES = 5000


def _root() -> str:
    path = get_settings().storage_dir
    os.makedirs(path, exist_ok=True)
    return path


def max_bytes() -> int:
    return get_settings().max_upload_mb * 1024 * 1024


def _ooxml_ok(data: bytes, folder: str) -> bool:
    import io
    import zipfile

    if not data.startswith(b"PK\x03\x04"):
        return False
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names = z.namelist()
            if len(names) > MAX_ZIP_ENTRIES or "[Content_Types].xml" not in names:
                return False
            # A zip bomb or an executable dressed as a document is refused.
            if sum(i.file_size for i in z.infolist()) > 20 * max(len(data), 1024 * 1024):
                return False
            return any(n.startswith(folder) for n in names) and not any(n.lower().endswith((".exe", ".dll", ".js", ".vbs"))
                                                                       for n in names)
    except (zipfile.BadZipFile, ValueError, OSError):
        return False


def _text_ok(data: bytes) -> bool:
    if b"\x00" in data:
        return False
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def check(content_type: str, data: bytes, size: int | None = None) -> str | None:
    """`data` is the whole file. The declared type must be allowed and match the content."""
    size = len(data) if size is None else size
    if content_type not in ALLOWED:
        return "Этот тип файла нельзя загрузить"
    if size > max_bytes():
        return f"Файл больше {get_settings().max_upload_mb} МБ"
    if size == 0:
        return "Пустой файл"
    mismatch = "Содержимое файла не совпадает с его типом"
    if content_type in OOXML:
        return None if _ooxml_ok(data, OOXML[content_type]) else mismatch
    if content_type == "text/plain":
        return None if _text_ok(data) else mismatch
    sigs = MAGIC.get(content_type)
    if sigs and not any(data[off:off + len(sig)] == sig for off, sig in sigs):
        return mismatch
    if content_type == "image/webp" and data[8:12] != b"WEBP":
        return mismatch
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


def _sig(key: str, exp: int, name: str = "") -> str:
    msg = f"file:{key}:{exp}" + (f":{name}" if name else "")
    return hmac.new(get_settings().jwt_secret.encode(), msg.encode(), hashlib.sha256).hexdigest()[:32]


def signed_url(key: str | None, ttl: int = 600, name: str | None = None) -> str | None:
    """name: the file name the download is saved under (part of the signature, so it can't be swapped)."""
    if not key:
        return None
    if key.startswith("http"):
        return key
    exp = int(time.time()) + ttl
    name = (name or "")[:200]
    q = f"exp={exp}&sig={_sig(key, exp, name)}" + (f"&name={quote(name)}" if name else "")
    return f"/api/files/{key}?{q}"


def verify(key: str, exp: int, sig: str, name: str = "") -> bool:
    return exp >= time.time() and hmac.compare_digest(_sig(key, exp, name), sig)


def download_name(key: str, name: str | None) -> str:
    """A safe file name for Content-Disposition, always with the extension of the stored type."""
    ext = os.path.splitext(key)[1]
    base = "".join(ch for ch in (name or "") if ch.isprintable() and ch not in '\\/:*?"<>|').strip(" .")[:150] or "file"
    root, given_ext = os.path.splitext(base)
    return (root if given_ext.lower() == ext.lower() else base) + ext
