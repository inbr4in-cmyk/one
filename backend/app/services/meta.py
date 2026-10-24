"""Meta Graph API: WhatsApp Cloud API and Instagram Messaging. Network calls only when configured."""

import hashlib
import hmac
import logging

import httpx

from app.core.config import get_settings

log = logging.getLogger("meta")
GRAPH = "https://graph.facebook.com/v21.0"


def verify_signature(body: bytes, header: str | None) -> bool:
    """X-Hub-Signature-256: sha256=<hmac of the raw body with the app secret>."""
    if not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(get_settings().meta_app_secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.removeprefix("sha256="))


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


async def wa_send_text(to_phone: str, text: str) -> SendResult:
    s = get_settings()
    if not (s.wa_phone_number_id and s.wa_access_token):
        log.info("WA (dev) -> %s: %s", to_phone, text[:60])
        return SendResult(True, external_id=None)
    return await _post(
        f"{GRAPH}/{s.wa_phone_number_id}/messages",
        s.wa_access_token,
        {"messaging_product": "whatsapp", "to": to_phone.lstrip("+"), "type": "text", "text": {"body": text}},
    )


async def wa_send_template(to_phone: str, name: str, locale: str, params: list[str]) -> SendResult:
    s = get_settings()
    if not (s.wa_phone_number_id and s.wa_access_token):
        log.info("WA template (dev) -> %s: %s %s", to_phone, name, params)
        return SendResult(True)
    lang = {"ru": "ru", "kk": "kk"}.get(locale, "ru")
    return await _post(
        f"{GRAPH}/{s.wa_phone_number_id}/messages",
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


async def ig_send_text(recipient_id: str, text: str, human_agent: bool = False) -> SendResult:
    """human_agent: Instagram allows a person (not a bot) to answer up to 7 days after the client's message."""
    s = get_settings()
    if not s.ig_access_token:
        log.info("IG (dev) -> %s: %s", recipient_id, text[:60])
        return SendResult(True)
    payload: dict = {"recipient": {"id": recipient_id}, "message": {"text": text}}
    if human_agent:
        payload |= {"messaging_type": "MESSAGE_TAG", "tag": "HUMAN_AGENT"}
    return await _post(f"{GRAPH}/me/messages", s.ig_access_token, payload)
