"""Push notifications through Firebase Cloud Messaging HTTP v1 (Android directly, iOS via APNs).

The push worker (app.jobs, every few seconds) sends notifications that have not been pushed yet. Without a
service-account file pushes are only logged, so dev and tests never call Google.
"""

import json
import logging
import time
from datetime import timedelta

import httpx
import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import AuthSession, DeviceToken, Notification
from app.services.clock import now

log = logging.getLogger("push")
_token: tuple[str, float] | None = None


def _credentials() -> dict | None:
    path = get_settings().fcm_credentials_file
    if not path:
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


async def _access_token(creds: dict) -> str:
    """OAuth token for the service account (cached ~55 min)."""
    global _token
    if _token and _token[1] > time.time() + 60:
        return _token[0]
    iat = int(time.time())
    assertion = jwt.encode({"iss": creds["client_email"], "scope": "https://www.googleapis.com/auth/firebase.messaging",
                            "aud": creds["token_uri"], "iat": iat, "exp": iat + 3600}, creds["private_key"], algorithm="RS256")
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(creds["token_uri"], data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                                                   "assertion": assertion})
        r.raise_for_status()
        data = r.json()
    _token = (data["access_token"], time.time() + int(data.get("expires_in", 3600)))
    return _token[0]


async def send(token: str, title: str, body: str | None, link: str | None, kind: str) -> str:
    """Returns "ok", "invalid" (drop the token) or "error" (retry later)."""
    creds = _credentials()
    if creds is None:
        log.info("push (dev) -> %s…: %s", token[:12], title)
        return "ok"
    msg = {"message": {"token": token, "notification": {"title": title, "body": body or ""},
                       "data": {"link": link or "", "kind": kind},
                       "android": {"priority": "high", "notification": {"channel_id": "default"}},
                       "apns": {"payload": {"aps": {"sound": "default"}}}}}
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(f"https://fcm.googleapis.com/v1/projects/{creds['project_id']}/messages:send",
                             headers={"Authorization": f"Bearer {await _access_token(creds)}"}, json=msg)
    except httpx.HTTPError as e:
        log.warning("push failed: %s", e)
        return "error"
    if r.status_code == 200:
        return "ok"
    if r.status_code in (400, 404) and ("UNREGISTERED" in r.text or "INVALID_ARGUMENT" in r.text):
        return "invalid"
    log.warning("push %s: %s", r.status_code, r.text[:200])
    return "error"


async def push_pending(db: AsyncSession) -> int:
    """Push fresh notifications (last 10 min) to every phone of their user. Idempotent via pushed_at."""
    rows = list(await db.scalars(select(Notification).where(Notification.pushed_at.is_(None),
                                                            Notification.at > now() - timedelta(minutes=10))
                                 .order_by(Notification.id).limit(500)))
    if not rows:
        return 0
    tokens: dict[int, list[DeviceToken]] = {}
    live = select(AuthSession.id).where(AuthSession.revoked_at.is_(None), AuthSession.expires_at > now())
    for t in await db.scalars(select(DeviceToken).where(DeviceToken.user_id.in_({n.user_id for n in rows}),
                                                        DeviceToken.session_id.in_(live))):  # logged-out phones get nothing
        tokens.setdefault(t.user_id, []).append(t)
    sent = 0
    for n in rows:
        ok = True
        for t in list(tokens.get(n.user_id, [])):
            res = await send(t.token, n.title, n.body, n.link, n.kind)
            if res == "invalid":
                tokens[n.user_id].remove(t)
                await db.delete(t)
            elif res == "error":
                ok = False
            else:
                sent += 1
        if ok:
            n.pushed_at = now()
    await db.commit()
    return sent
