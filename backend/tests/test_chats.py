from sqlalchemy import select

from app.core.security import hash_password
from app.models import AuditLog, ChatMember, User
from tests.conftest import branch_id, level_id, login, make_staff

YANGI = "Янги шахар"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


async def _portal_login(db, client, user_id: int) -> dict:
    u = await db.get(User, user_id)
    u.password_hash = hash_password("Secret-pass-123")
    await db.flush()
    return await login(client, u.phone)


async def _world(db, client, owner_h):
    bid = await branch_id(db, YANGI)
    teacher = await make_staff(db, "teacher", [YANGI], "+77020000011", "Дана Учитель")
    g = (await client.post("/api/groups", headers=owner_h, json={
        "name": "EL-7", "branch_id": bid, "level_id": await level_id(db, "ELE"), "teacher_id": teacher.id, "capacity": 12})).json()
    kids = []
    for i, name in enumerate(["Алия", "Тимур"]):
        r = await client.post("/api/students", headers=owner_h, json={
            "full_name": name, "phone": f"+7705111220{i}", "branch_id": bid, "level_id": await level_id(db, "ELE"),
            "guardians": [{"full_name": f"Родитель {name}", "phone": f"+7705999000{i}", "relation": "мама"}]})
        assert r.status_code == 201, r.text
        s = r.json()
        assert (await client.post(f"/api/groups/{g['id']}/members", headers=owner_h, json={"student_id": s["id"]})).status_code == 201
        kids.append(s)
    return bid, teacher, g, kids


async def test_hard_chat_rules(db, client, owner_h):
    _, teacher, g, (a, b) = await _world(db, client, owner_h)
    sa = await _portal_login(db, client, a["user_id"])
    pa = await _portal_login(db, client, a["guardians"][0]["user_id"])
    # Student ↔ student and parent ↔ other parent are locked forever
    r = await client.post("/api/chats/direct", headers=sa, json={"user_id": b["user_id"]})
    assert r.status_code == 403
    r = await client.post("/api/chats/direct", headers=pa, json={"user_id": b["guardians"][0]["user_id"]})
    assert r.status_code == 403
    # A parent may not write to someone else's child
    r = await client.post("/api/chats/direct", headers=pa, json={"user_id": b["user_id"]})
    assert r.status_code == 403
    denied = (await db.scalars(select(AuditLog).where(AuditLog.action == "chat.denied"))).all()
    assert len(denied) == 3
    # A parent may write to their child's teacher
    contacts = (await client.get("/api/chats/contacts", headers=pa)).json()
    assert teacher.id in {c["id"] for c in contacts}
    assert b["guardians"][0]["user_id"] not in {c["id"] for c in contacts}
    r = await client.post("/api/chats/direct", headers=pa, json={"user_id": teacher.id})
    assert r.status_code == 200, r.text
    chat = r.json()
    r = await client.post(f"/api/chats/{chat['id']}/messages", headers=pa, json={"text": "Здравствуйте! Как успехи?"})
    assert r.status_code == 201
    th = await login(client, teacher.phone)
    mine = (await client.get("/api/chats", headers=th)).json()
    assert any(c["id"] == chat["id"] and c["unread"] == 1 for c in mine)
    assert (await client.get("/api/counters", headers=th)).json()["chats"] >= 1
    # The student group chat exists and both kids are in it; nobody else's parent sees it
    group_chat = next(c for c in mine if c["kind"] == "group")
    assert group_chat["members"] == 3  # teacher + 2 students
    r = await client.get(f"/api/chats/{group_chat['id']}/messages", headers=pa)
    assert r.status_code == 404


async def test_group_chat_follows_membership_and_monitor_is_audited(db, client, owner_h):
    _, teacher, g, (a, b) = await _world(db, client, owner_h)
    th = await login(client, teacher.phone)
    group_chat = next(c for c in (await client.get("/api/chats", headers=th)).json() if c["kind"] == "group")
    r = await client.post(f"/api/chats/{group_chat['id']}/messages", headers=th, json={"text": "Домашка на стр. 12"})
    msg = r.json()
    assert (await client.post(f"/api/chat-messages/{msg['id']}/pin", headers=th)).json()["pinned"] is True
    assert len((await client.get(f"/api/chats/{group_chat['id']}/pinned", headers=th)).json()) == 1

    sb = await _portal_login(db, client, b["user_id"])
    assert (await client.get(f"/api/chats/{group_chat['id']}/messages", headers=sb)).status_code == 200
    assert (await client.delete(f"/api/groups/{g['id']}/members/{b['id']}", headers=owner_h)).status_code == 204
    left = await db.scalar(select(ChatMember).where(ChatMember.chat_id == group_chat["id"], ChatMember.user_id == b["user_id"]))
    assert left.left_on is not None
    assert (await client.get(f"/api/chats/{group_chat['id']}/messages", headers=sb)).status_code == 404

    # Owner is not a member: read-only view, logged, hidden messages visible for quality control
    sa = await _portal_login(db, client, a["user_id"])
    m2 = (await client.post(f"/api/chats/{group_chat['id']}/messages", headers=sa, json={"text": "ой"})).json()
    assert (await client.delete(f"/api/chat-messages/{m2['id']}", headers=sa)).status_code == 204
    view = (await client.get(f"/api/chats/{group_chat['id']}/messages", headers=owner_h)).json()
    assert any(m["hidden"] and m["text"] == "ой" for m in view)
    student_view = (await client.get(f"/api/chats/{group_chat['id']}/messages", headers=sa)).json()
    assert all(m["text"] is None for m in student_view if m["hidden"])
    assert (await client.post(f"/api/chats/{group_chat['id']}/messages", headers=owner_h, json={"text": "x"})).status_code == 403
    logs = (await db.scalars(select(AuditLog).where(AuditLog.action == "chat.monitor_view"))).all()
    assert len(logs) == 1 and logs[0].entity_id == group_chat["id"]


async def test_file_upload_checks_type_and_signature(db, client, owner_h, tmp_path, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "storage_dir", str(tmp_path))
    # Declared PNG but the bytes are a script → rejected
    r = await client.post("/api/files", headers=owner_h, files={"file": ("a.png", b"<script>alert(1)</script>", "image/png")})
    assert r.status_code == 400
    r = await client.post("/api/files", headers=owner_h, files={"file": ("a.html", b"<html></html>", "text/html")})
    assert r.status_code == 400
    r = await client.post("/api/files", headers=owner_h, files={"file": ("a.png", PNG, "image/png")})
    assert r.status_code == 201, r.text
    url = r.json()["url"]
    assert (await client.get(url)).status_code == 200
    assert (await client.get(url.replace("sig=", "sig=0"))).status_code == 403
    key = r.json()["key"]
    assert (await client.get(f"/api/files/{key}?exp=9999999999&sig=deadbeef")).status_code == 403


def test_phone_detector():
    from app.services.chats import has_phone
    for t in ("+7 701 234 56 78", "87012345678", "мой номер 8(701)234-56-78", "+7 7Д01 234 56 78", "7О1 234 5б 78 99"):
        assert has_phone(t), t
    for t in (None, "", "Домашка на стр. 12, упр. 3 и 4", "Урок в 15:30, кабинет 2", "оооооооооооооо", "2024 2025 года"):
        assert not has_phone(t), t


async def test_student_cannot_send_phone_and_chat_metadata(db, client, owner_h):
    _, teacher, g, (a, b) = await _world(db, client, owner_h)
    th = await login(client, teacher.phone)
    group_chat = next(c for c in (await client.get("/api/chats", headers=th)).json() if c["kind"] == "group")
    sa = await _portal_login(db, client, a["user_id"])
    r = await client.post(f"/api/chats/{group_chat['id']}/messages", headers=sa, json={"text": "пиши мне +7 7Д01 234 56 78"})
    assert r.status_code == 400
    msg = (await client.post(f"/api/chats/{group_chat['id']}/messages", headers=th, json={"text": "Звоните 87012345678"})).json()
    assert msg["sender_position"] == teacher.position
    pa = await _portal_login(db, client, a["guardians"][0]["user_id"])
    chat = (await client.post("/api/chats/direct", headers=pa, json={"user_id": teacher.id})).json()
    mine = (await client.get("/api/chats", headers=pa)).json()
    assert next(c for c in mine if c["id"] == chat["id"])["about_student_id"] == a["id"]
