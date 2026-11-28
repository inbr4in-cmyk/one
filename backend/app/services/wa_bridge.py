"""WhatsApp linked by QR ("как WhatsApp Web"): the local link service (wa/bridge.mjs) keeps the session, this module talks
to it. Unofficial protocol, chosen by the owner on 25.11.2026 for the school's main number: managers' manual answers only.
Notifications, login codes and templates never go this way (meta.wa_configured() stays as it was)."""
import hmac
import logging
import time

import httpx

from app.core.config import get_settings
from app.services.meta import SendResult

log = logging.getLogger("wa_bridge")


def enabled() -> bool:
    s = get_settings()
    return bool(s.wa_bridge_url and len(s.wa_bridge_secret) >= 24)


def verify(header: str | None) -> bool:
    secret = get_settings().wa_bridge_secret
    return bool(len(secret) >= 24 and header and hmac.compare_digest(secret.encode(), header.encode()))


async def _call(method: str, path: str, json: dict | None = None, timeout: float = 20) -> dict:
    s = get_settings()
    async with httpx.AsyncClient(timeout=timeout) as c:
        r = await c.request(method, s.wa_bridge_url.rstrip("/") + path, json=json, headers={"x-bridge-secret": s.wa_bridge_secret})
    data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    if r.status_code >= 400:
        raise RuntimeError(str(data.get("error") or f"HTTP {r.status_code}"))
    return data


OFF = {"state": "off", "qr": None, "me": None, "linked_at": None, "pending": 0, "last_close": None}


async def statuses() -> dict[int, dict] | None:
    """Every linked number by its line: 0 is the number linked before branches had their own, otherwise the line is
    the branch id. None: the link service is switched off or does not answer."""
    if not enabled():
        return None
    try:
        data = await _call("GET", "/status", timeout=5)
    except (httpx.HTTPError, RuntimeError, ValueError):
        return None
    lines = data.get("lines") if isinstance(data.get("lines"), dict) else {}
    return {int(k): v for k, v in lines.items() if str(k).isdigit() and isinstance(v, dict)}


async def status(line: int = 0) -> dict:
    """One number's state for the settings page. «unavailable»: the service itself does not answer."""
    if not enabled():
        return {**OFF, "state": "disabled"}
    all_ = await statuses()
    return {**OFF, "state": "unavailable"} if all_ is None else all_.get(line, OFF)


_linked: tuple[float, frozenset[int]] = (0.0, frozenset())


async def linked_lines() -> frozenset[int]:
    """The lines linked right now. Remembered for a few seconds: the inbox asks for every chat."""
    global _linked
    if not enabled():
        return frozenset()
    if time.monotonic() - _linked[0] > 5:
        all_ = await statuses() or {}
        _linked = (time.monotonic(), frozenset(k for k, v in all_.items() if v.get("state") == "open"))
    return _linked[1]


async def linked(line: int = 0) -> bool:
    return line in await linked_lines()


def forget() -> None:
    global _linked
    _linked = (0.0, frozenset())


async def start(line: int = 0) -> dict:
    return await _call("POST", "/start", {"line": line})


async def logout(line: int = 0) -> dict:
    return await _call("POST", "/logout", {"line": line})


async def send_text(chat: str, text: str, line: int = 0) -> SendResult:
    """chat: the contact's id as the link service gave it — the phone in digits, or «lid:…»."""
    try:
        data = await _call("POST", "/send", {"line": line, "to": chat.lstrip("+"), "text": text}, timeout=40)
        return SendResult(True, external_id=data.get("id"))
    except (httpx.HTTPError, RuntimeError, ValueError) as e:
        return SendResult(False, error=str(e)[:250] or "WhatsApp не подключён")
