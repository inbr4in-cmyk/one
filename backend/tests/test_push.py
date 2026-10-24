from sqlalchemy import select

from app.models import DeviceToken, Notification
from app.services import push
from app.services.messaging import notify_user
from tests.test_chats import _portal_login, _world


async def test_push_registered_device_once_and_not_after_logout(db, client, owner_h, monkeypatch):
    sent = []

    async def fake_send(token, title, body, link, kind):
        sent.append((token, title))
        return "ok"

    monkeypatch.setattr(push, "send", fake_send)
    _, _, _, (a, _) = await _world(db, client, owner_h)
    pa = await _portal_login(db, client, a["guardians"][0]["user_id"])
    tok = "fcm-token-" + "x" * 30
    assert (await client.post("/api/auth/devices", headers=pa, json={"platform": "android", "token": tok})).status_code == 204
    uid = a["guardians"][0]["user_id"]
    await db.execute(Notification.__table__.update().values(pushed_at=push.now()))  # older noise
    await notify_user(db, uid, "attendance", "Алия не пришла на урок")
    await db.flush()
    assert await push.push_pending(db) == 1 and await push.push_pending(db) == 0
    assert sent == [(tok, "Алия не пришла на урок")]
    await client.post("/api/auth/logout", headers=pa)
    await notify_user(db, uid, "chat", "Новое сообщение")
    await db.flush()
    assert await push.push_pending(db) == 0
    assert await db.scalar(select(DeviceToken).where(DeviceToken.token == tok))
