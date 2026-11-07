import hashlib
import hmac
import json
from datetime import timedelta

from sqlalchemy import func, select

from app.core.config import get_settings
from app.models import Accrual, Conversation, ExternalContact, Lead, LeadStage, Lesson, Question, Room, Test
from app.services.clock import now
from tests.conftest import branch_id, level_id, login, make_staff

YANGI = "Янги шахар"


def signed(payload: dict) -> tuple[bytes, dict]:
    body = json.dumps(payload).encode()
    sig = hmac.new(get_settings().meta_app_secret.encode(), body, hashlib.sha256).hexdigest()
    return body, {"X-Hub-Signature-256": f"sha256={sig}", "Content-Type": "application/json"}


def wa_payload(wa_id: str, mid: str, text: str, name: str = "Асель") -> dict:
    return {"object": "whatsapp_business_account", "entry": [{"changes": [{"value": {
        "contacts": [{"wa_id": wa_id, "profile": {"name": name}}],
        "messages": [{"from": wa_id, "id": mid, "timestamp": str(int(now().timestamp())), "type": "text", "text": {"body": text}}],
    }}]}]}


def ig_payload(sender: str, mid: str, text: str) -> dict:
    return {"object": "instagram", "entry": [{"messaging": [{"sender": {"id": sender}, "timestamp": int(now().timestamp() * 1000),
                                                             "message": {"mid": mid, "text": text}}]}]}


async def test_webhook_rejects_bad_signature(client, db):
    r = await client.post("/api/webhooks/meta", content=json.dumps(wa_payload("77011112233", "m1", "hi")),
                          headers={"X-Hub-Signature-256": "sha256=deadbeef", "Content-Type": "application/json"})
    assert r.status_code == 401
    assert await db.scalar(select(func.count()).select_from(Lead)) == 0


async def test_whatsapp_message_creates_lead_once(client, db):
    body, h = signed(wa_payload("77011112233", "wamid.1", "Здравствуйте, сколько стоит курс?"))
    assert (await client.post("/api/webhooks/meta", content=body, headers=h)).json()["stored"] == 1
    # Meta retry of the same message → nothing new
    assert (await client.post("/api/webhooks/meta", content=body, headers=h)).json()["stored"] == 0
    body, h = signed(wa_payload("77011112233", "wamid.2", "Есть группы вечером?"))
    await client.post("/api/webhooks/meta", content=body, headers=h)
    leads = list(await db.scalars(select(Lead)))
    assert len(leads) == 1 and leads[0].source == "whatsapp" and leads[0].phone == "+77011112233"
    conv = await db.scalar(select(Conversation))
    assert conv.unread == 2


async def test_instagram_lead_and_reply_window(client, db, owner_h):
    body, h = signed(ig_payload("17841400000000001", "ig.m1", "Хочу на пробный"))
    await client.post("/api/webhooks/meta", content=body, headers=h)
    convs = (await client.get("/api/inbox/conversations", headers=owner_h)).json()
    assert len(convs) == 1 and convs[0]["channel"] == "instagram" and convs[0]["lead"]["source"] == "instagram"
    cid = convs[0]["id"]
    r = await client.post(f"/api/inbox/conversations/{cid}/messages", headers=owner_h, json={"text": "Здравствуйте! Когда удобно?"})
    assert r.status_code == 201
    lead = await db.scalar(select(Lead))
    st = await db.get(LeadStage, lead.stage_id)
    assert st.code == "contacted" and lead.owner_id is not None  # first responder owns the lead
    conv = await db.get(Conversation, cid)
    conv.last_inbound_at = now() - timedelta(days=8)  # Instagram: a person may answer for 7 days
    await db.flush()
    r = await client.post(f"/api/inbox/conversations/{cid}/messages", headers=owner_h, json={"text": "Вы тут?"})
    assert r.status_code == 409


async def test_existing_student_does_not_become_lead(client, db, owner_h):
    bid = await branch_id(db, YANGI)
    r = await client.post("/api/students", headers=owner_h, json={"full_name": "Ерлан", "phone": "+77019998877", "branch_id": bid})
    assert r.status_code == 201
    body, h = signed(wa_payload("77019998877", "wamid.x", "Добрый день"))
    await client.post("/api/webhooks/meta", content=body, headers=h)
    assert await db.scalar(select(func.count()).select_from(Lead)) == 0
    c = await db.scalar(select(ExternalContact))
    assert c.student_id == r.json()["id"]


async def test_trial_bonus_once_and_sale_bonus(db, client, owner_h):
    bid = await branch_id(db, YANGI)
    sales = await make_staff(db, "sales", [YANGI], "+77080000001", "Продажник")
    teacher = await make_staff(db, "teacher", [YANGI], "+77080000002", "Учитель")
    office = await make_staff(db, "office_manager", [YANGI], "+77080000003", "Офис")
    sh, th, oh = await login(client, sales.phone), await login(client, teacher.phone), await login(client, office.phone)
    lead = (await client.post("/api/crm/leads", headers=sh, json={"full_name": "Мадина", "phone": "+77017776655", "branch_id": bid,
                                                               "age": 25})).json()
    dup = await client.post("/api/crm/leads", headers=sh, json={"full_name": "Мадина 2", "phone": "87017776655", "branch_id": bid})
    assert dup.status_code == 409
    g = (await client.post("/api/groups", headers=owner_h, json={"name": "EL-1", "branch_id": bid,
                                                                 "level_id": await level_id(db, "ELE"), "teacher_id": teacher.id})).json()
    room = await db.scalar(select(Room).where(Room.branch_id == bid))
    lesson = Lesson(branch_id=bid, group_id=g["id"], level_id=g["level_id"], teacher_id=teacher.id, room_id=room.id,
                    starts_at=now() + timedelta(minutes=30), ends_at=now() + timedelta(minutes=120))
    db.add(lesson)
    await db.flush()
    r = await client.post(f"/api/crm/leads/{lead['id']}/trial", headers=sh, json={"lesson_id": lesson.id})
    assert r.status_code == 200, r.text
    lesson.starts_at = now() - timedelta(minutes=5)
    await db.flush()
    roster = (await client.get(f"/api/lessons/{lesson.id}/attendance", headers=th)).json()
    assert roster["rows"][0]["is_trial"] is True
    for _ in range(2):  # re-marking must not pay twice
        r = await client.put(f"/api/lessons/{lesson.id}/attendance", headers=th,
                             json={"marks": [{"lead_id": lead["id"], "status": "present"}]})
        assert r.status_code == 200, r.text
    bonuses = list(await db.scalars(select(Accrual).where(Accrual.kind == "trial_visit")))
    assert len(bonuses) == 1 and bonuses[0].user_id == sales.id and bonuses[0].amount == 2000
    # Sales person can't sell; office manager converts and takes the first payment
    sid = (await client.post(f"/api/crm/leads/{lead['id']}/convert", headers=oh, json={})).json()["student_id"]
    await client.post(f"/api/groups/{g['id']}/members", headers=oh, json={"student_id": sid})
    assert (await client.post("/api/payments", headers=sh, json={"student_id": sid, "lessons": 8, "method": "cash"})).status_code == 403
    r = await client.post("/api/payments", headers=oh, json={"student_id": sid, "lessons": 8, "method": "kaspi"})
    assert r.status_code == 201, r.text
    kinds = {(a.kind, a.user_id, a.amount) for a in await db.scalars(select(Accrual))}
    assert ("sale", office.id, 2000) in kinds and ("trial_retention", teacher.id, 500) in kinds
    lead_row = await db.get(Lead, lead["id"])
    assert (await db.get(LeadStage, lead_row.stage_id)).code == "paid"
    # Refund reverses the sale-linked bonuses
    pid = r.json()["id"]
    rr = await client.post(f"/api/payments/{pid}/refund", headers=owner_h, json={"lessons": 8, "amount": 24000, "reason": "Переезд"})
    assert rr.status_code == 201 and rr.json()["bonuses_reversed"] == 2


async def test_qr_placement_creates_lead(db, client, owner_h):
    t = Test(kind="placement", title="Тест уровня", max_score=3, is_published=True,
             scale=[{"min": 0, "level_id": await level_id(db, "BEG")}, {"min": 2, "level_id": await level_id(db, "ELE")}])
    db.add(t)
    await db.flush()
    for i in range(3):
        db.add(Question(test_id=t.id, order=i, kind="single", text=f"Q{i}", options=["a", "b", "c"], correct=[1], points=1))
    await db.flush()
    bid = await branch_id(db, "Север")
    token = (await client.get(f"/api/branches/{bid}/qr", headers=owner_h)).json()["token"]
    assert (await client.get("/api/public/placement/1-forged")).status_code == 404
    pub = (await client.get(f"/api/public/placement/{token}")).json()
    assert "correct" not in pub["questions"][0]
    st = (await client.post(f"/api/public/placement/{token}/start", json={"name": "Тимур", "phone": "87075554433", "age": 16,
                                                                          "consent": True})).json()
    answers = {str(q["id"]): [1] for q in pub["questions"][:2]}
    r = await client.post("/api/public/placement/submit", json={"attempt_token": st["attempt_token"], "answers": answers})
    assert r.json() == {"score": 2, "max": 3, "level": "Elementary"}
    lead = await db.scalar(select(Lead))
    assert lead.source == "qr" and lead.branch_id == bid and lead.placement_score == 2
    again = await client.post("/api/public/placement/submit", json={"attempt_token": st["attempt_token"], "answers": answers})
    assert again.status_code == 400


def test_ig_graph_host_follows_token_type():
    from app.services.meta import _graph, _ig_graph
    assert _ig_graph("IGAAxyz").startswith("https://graph.instagram.com/")
    assert _ig_graph("EAAxyz").startswith("https://graph.facebook.com/")
    assert _graph().startswith("https://graph.facebook.com/v")
