"""Meta Graph API: WhatsApp Cloud API and Instagram Messaging. Network calls only when configured."""

import hashlib
import hmac
import logging
import os
import time
from pathlib import Path

import httpx

from app.core.config import get_settings

log = logging.getLogger("meta")


def _graph() -> str:
    return f"https://graph.facebook.com/{get_settings().meta_graph_version}"


def _ig_graph(token: str) -> str:
    """Instagram-login tokens (IGAA...) go to graph.instagram.com; Page tokens (Facebook login) to graph.facebook.com."""
    host = "graph.instagram.com" if token.startswith("IG") else "graph.facebook.com"
    return f"https://{host}/{get_settings().meta_graph_version}"


def verify_signature(body: bytes, header: str | None) -> bool:
    """X-Hub-Signature-256: sha256=<hmac of the raw body with the app secret>. Instagram-login webhooks are signed
    with the Instagram app secret, the rest with the Meta app secret: either one is accepted."""
    if not header or not header.startswith("sha256="):
        return False
    got, s = header.removeprefix("sha256="), get_settings()
    for secret in (s.meta_app_secret, s.ig_app_secret):
        if secret and hmac.compare_digest(hmac.new(secret.encode(), body, hashlib.sha256).hexdigest(), got):
            return True
    return False


# An Instagram-login token lives 60 days and is renewed by the nightly job. The renewed token is kept in a file
# readable only by the service user (the env file belongs to root); a token typed in again by the owner replaces it.
def _ig_token_file() -> Path:
    return Path(get_settings().storage_dir) / ".ig_token"


def ig_token() -> str:
    env = get_settings().ig_access_token
    try:
        saved = _ig_token_file().read_text().strip().split("\n")
    except OSError:
        return env
    # line 1: fingerprint of the env token it was renewed from, line 2: the renewed token
    if len(saved) == 2 and saved[0] == hashlib.sha256(env.encode()).hexdigest() and saved[1]:
        return saved[1]
    return env


async def ig_refresh(min_age_days: int = 7) -> str:
    """Renews the Instagram-login token. Returns what happened, never the token."""
    token = ig_token()
    if not token.startswith("IG"):
        return "not an Instagram-login token"
    f = _ig_token_file()
    if f.exists() and time.time() - f.stat().st_mtime < min_age_days * 86400:
        return "fresh"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get("https://graph.instagram.com/refresh_access_token",
                                 params={"grant_type": "ig_refresh_token", "access_token": token})
        data = r.json()
    except (httpx.HTTPError, ValueError) as e:
        log.warning("Instagram token renewal failed: %s", str(e)[:200])
        return "failed"
    new = data.get("access_token") if isinstance(data, dict) else None
    if r.status_code >= 400 or not isinstance(new, str) or not new:
        log.warning("Instagram token renewal refused: %s", str((data.get("error") or {}).get("message", r.status_code))[:200])
        return "refused"
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as out:
        out.write(hashlib.sha256(get_settings().ig_access_token.encode()).hexdigest() + "\n" + new + "\n")
    os.replace(tmp, f)
    return "renewed"


class SendResult:
    def __init__(self, ok: bool, external_id: str | None = None, error: str | None = None) -> None:
        self.ok, self.external_id, self.error = ok, external_id, error


async def _post(url: str, token: str, payload: dict) -> SendResult:
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(url, json=payload, headers={"Authorization": f"Bearer {token}"})
        data = r.json()
        if r.status_code >= 400:
            return SendResult(False, error=str(data.get("error", {}).get("message", r.status_code))[:250])
        mid = (data.get("messages") or [{}])[0].get("id") or data.get("message_id")
        return SendResult(True, external_id=mid)
    except (httpx.HTTPError, ValueError) as e:  # network or bad JSON
        return SendResult(False, error=str(e)[:250])


def wa_configured() -> bool:
    s = get_settings()
    return bool(s.wa_phone_number_id and s.wa_access_token)


def _not_configured(what: str, to: str) -> SendResult:
    """Without keys nothing is sent. The text is never logged: it may hold a one-time code.
    In production this is a failure (visible in the delivery log), in dev a no-op success."""
    if get_settings().is_prod:
        return SendResult(False, error="WhatsApp не подключён")
    log.info("%s (dev, not sent) -> %s", what, to[-4:])
    return SendResult(True)


async def wa_send_text(to_phone: str, text: str) -> SendResult:
    s = get_settings()
    if not wa_configured():
        return _not_configured("WA text", to_phone)
    return await _post(
        f"{_graph()}/{s.wa_phone_number_id}/messages",
        s.wa_access_token,
        {"messaging_product": "whatsapp", "to": to_phone.lstrip("+"), "type": "text", "text": {"body": text}},
    )


async def wa_send_template(to_phone: str, name: str, locale: str, params: list[str]) -> SendResult:
    s = get_settings()
    if not wa_configured():
        return _not_configured(f"WA template {name}", to_phone)
    lang = {"ru": "ru", "kk": "kk"}.get(locale, "ru")
    return await _post(
        f"{_graph()}/{s.wa_phone_number_id}/messages",
        s.wa_access_token,
        {
            "messaging_product": "whatsapp",
            "to": to_phone.lstrip("+"),
            "type": "template",
            "template": {
                "name": name,
                "language": {"code": lang},
                "components": [{"type": "body", "parameters": [{"type": "text", "text": p} for p in params]}],
            },
        },
    )


async def wa_send_auth_code(to_phone: str, name: str, locale: str, code: str) -> SendResult:
    """One-time code through an approved Authentication template (body {{1}} = code, copy-code button = code).
    Meta lets a business write first only with a template, so codes reach people who haven't written in 24 h."""
    s = get_settings()
    if not wa_configured():
        return _not_configured(f"WA auth {name}", to_phone)
    return await _post(
        f"{_graph()}/{s.wa_phone_number_id}/messages",
        s.wa_access_token,
        {
            "messaging_product": "whatsapp",
            "to": to_phone.lstrip("+"),
            "type": "template",
            "template": {
                "name": name,
                "language": {"code": {"kk": "kk"}.get(locale, "ru")},
                "components": [
                    {"type": "body", "parameters": [{"type": "text", "text": code}]},
                    {"type": "button", "sub_type": "url", "index": "0", "parameters": [{"type": "text", "text": code}]},
                ],
            },
        },
    )


async def ig_send_text(recipient_id: str, text: str, human_agent: bool = False, comment_id: str | None = None) -> SendResult:
    """human_agent: Instagram allows a person (not a bot) to answer up to 7 days after the client's message.
    comment_id: a private reply to a comment (one per comment, within 7 days); it opens a Direct chat with its author."""
    s = get_settings()
    token = ig_token()
    if not token:
        if s.is_prod:
            return SendResult(False, error="Instagram не подключён")
        log.info("IG (dev, not sent) -> %s", recipient_id[-4:])
        return SendResult(True)
    payload: dict = {"recipient": {"comment_id": comment_id} if comment_id else {"id": recipient_id}, "message": {"text": text}}
    if human_agent and not comment_id:
        payload |= {"messaging_type": "MESSAGE_TAG", "tag": "HUMAN_AGENT"}
    sender = s.ig_page_id if s.ig_page_id and not token.startswith("IG") else "me"
    return await _post(f"{_ig_graph(token)}/{sender}/messages", token, payload)
