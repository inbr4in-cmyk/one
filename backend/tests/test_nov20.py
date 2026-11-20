from datetime import timedelta

from sqlalchemy import select

from app.models import Accrual, GroupMember, Lesson
from app.services.clock import local, today
from tests.conftest import branch_id, level_id, make_staff

YANGI = "Янги шахар"


async def test_group_entered_late_gets_its_past_lessons_and_members_from_the_first_day(client, db, owner_h):
    from tests.test_core_learning import _setup, _student

    bid, teacher, room, g = await _setup(db, client, owner_h)
    start = today() - timedelta(days=7)
    rule = {"weekdays": list(range(7)), "start_time": "07:00", "end_time": "07:30", "room_id": room.id}
    too_old = (today() - timedelta(days=40)).isoformat()
    assert (await client.post(f"/api/groups/{g['id']}/schedule", headers=owner_h, json={**rule, "valid_from": too_old})).status_code == 400
    r = await client.post(f"/api/groups/{g['id']}/schedule", headers=owner_h, json={**rule, "valid_from": start.isoformat()})
    assert r.status_code == 201, r.text
    assert r.json()["past"] == 7
    days = sorted(local(x.starts_at).date() for x in await db.scalars(select(Lesson).where(Lesson.group_id == g["id"])))
    assert days[0] == start and len(set(days)) == len(days)
    assert (await client.get(f"/api/groups/{g['id']}", headers=owner_h)).json()["starts_on"] == start.isoformat()

    s = await _student(db, client, owner_h, bid, "Задним Числом", "+77051116001")
    m = f"/api/groups/{g['id']}/members"
    early = (start - timedelta(days=1)).isoformat()
    assert (await client.post(m, headers=owner_h, json={"student_id": s["id"], "joined_on": early})).status_code == 400
    assert (await client.post(m, headers=owner_h, json={"student_id": s["id"], "joined_on": start.isoformat()})).status_code == 201
    assert (await db.scalar(select(GroupMember).where(GroupMember.student_id == s["id"]))).joined_on == start
    first = await db.scalar(select(Lesson).where(Lesson.group_id == g["id"]).order_by(Lesson.starts_at))
    roster = (await client.get(f"/api/lessons/{first.id}/attendance", headers=owner_h)).json()
    assert [x["student_id"] for x in roster["rows"]] == [s["id"]]


async def test_individual_lesson_is_not_paid_when_the_student_did_not_come(client, db, owner_h):
    from tests.test_core_learning import _lesson_now, _student

    bid = await branch_id(db, YANGI)
    teacher = await make_staff(db, "teacher", [YANGI], "+77051116010", "Индив Учитель")
    from app.models import Room
    room = await db.scalar(select(Room).where(Room.branch_id == bid).order_by(Room.id))
    g = (await client.post("/api/groups", headers=owner_h, json={
        "name": "Индив 1", "branch_id": bid, "level_id": await level_id(db, "ELE"), "teacher_id": teacher.id,
        "room_id": room.id, "kind": "individual"})).json()
    s = await _student(db, client, owner_h, bid, "Один Ученик", "+77051116011")
    await client.post(f"/api/groups/{g['id']}/members", headers=owner_h, json={"student_id": s["id"]})
    lesson = await _lesson_now(db, g, teacher, room)
    lid = lesson.id

    async def pay(status):
        r = await client.put(f"/api/lessons/{lid}/attendance", headers=owner_h,
                             json={"marks": [{"student_id": s["id"], "status": status}], "reason": "исправление"})
        assert r.status_code == 200, r.text
        a = await db.scalar(select(Accrual).where(Accrual.kind == "lesson", Accrual.ref_id == lid))
        if a:
            await db.refresh(a)
        return a.amount if a else 0

    assert await pay("absent") == 0
    assert await pay("present") == 2000
    assert await pay("excused") == 0


async def test_lead_can_be_corrected_and_becomes_a_student_only_in_the_paid_column(client, db, owner_h):
    from app.services.crm import stage_by_code

    bid = await branch_id(db, YANGI)
    lead = (await client.post("/api/crm/leads", headers=owner_h, json={"full_name": "87051116020", "branch_id": bid})).json()
    r = await client.patch(f"/api/crm/leads/{lead['id']}", headers=owner_h, json={"full_name": "Айдана", "phone": "87051116020"})
    assert r.status_code == 200 and r.json()["full_name"] == "Айдана" and r.json()["phone"] == "+77051116020"
    assert (await client.patch(f"/api/crm/leads/{lead['id']}", headers=owner_h, json={"full_name": " "})).status_code == 400
    assert (await client.post(f"/api/crm/leads/{lead['id']}/convert", headers=owner_h, json={})).status_code == 400
    paid = await stage_by_code(db, "main", "paid")
    assert (await client.post(f"/api/crm/leads/{lead['id']}/stage", headers=owner_h, json={"stage_id": paid.id})).status_code == 200
    r = await client.post(f"/api/crm/leads/{lead['id']}/convert", headers=owner_h, json={})
    assert r.status_code == 200 and r.json()["student_id"]


async def test_refused_lead_is_booked_on_a_trial_again_and_the_card_shows_the_teacher(client, db, owner_h):
    from app.services.clock import now
    from app.services.crm import stage_by_code
    from tests.test_core_learning import _setup

    bid, teacher, room, g = await _setup(db, client, owner_h)
    lesson = Lesson(branch_id=bid, group_id=g["id"], level_id=g["level_id"], teacher_id=teacher.id, room_id=room.id,
                    starts_at=now() + timedelta(hours=2), ends_at=now() + timedelta(hours=3))
    db.add(lesson)
    await db.flush()
    lead = (await client.post("/api/crm/leads", headers=owner_h, json={"full_name": "Отказник", "branch_id": bid})).json()
    lost = await stage_by_code(db, "main", "lost")
    r = await client.post(f"/api/crm/leads/{lead['id']}/stage", headers=owner_h, json={"stage_id": lost.id, "lost_reason": "Дорого"})
    assert r.status_code == 200 and r.json()["lost_reason"] == "Дорого"
    r = await client.post(f"/api/crm/leads/{lead['id']}/trial", headers=owner_h, json={"lesson_id": lesson.id, "notify": False})
    assert r.status_code == 200, r.text
    card = r.json()
    booked = await stage_by_code(db, "main", "trial_booked")
    assert card["stage_id"] == booked.id and card["lost_reason"] is None and card["trial_teacher"] == teacher.full_name
    events = (await client.get(f"/api/crm/leads/{lead['id']}", headers=owner_h)).json()["events"]
    assert any("Дорого" in (e["text"] or "") for e in events)  # the refusal stays in the history


async def test_instagram_comment_makes_a_lead_only_when_it_asks_for_something(client, db, owner_h):
    from app.modules.inbox.service import comment_kind
    from tests.test_crm_inbox import signed

    words = "цена, сколько, +"
    assert comment_kind("😍🔥🔥", words) == "noise" and comment_kind("@aigerim @dana 👍", words) == "noise"
    assert comment_kind("+", words) == "lead" and comment_kind("Сколько стоит?", words) == "lead"
    assert comment_kind("Красиво получилось", words) == "plain" and comment_kind("Красиво", "") == "lead"

    def c(cid, text, who):
        return {"field": "comments", "value": {"id": cid, "text": text, "from": {"id": who, "username": f"u{who}"}}}

    body, h = signed({"object": "instagram", "entry": [{"id": "17841499999999999", "time": 1, "changes": [
        c("f1", "😍😍", "9101"), c("f2", "Молодцы, красиво!", "9102"), c("f3", "Хочу цену", "9103")]}]})
    r = await client.post("/api/webhooks/meta", content=body, headers=h)
    assert r.json()["stored"] == 2  # the emoji is dropped
    convs = {x["contact"]["username"]: x for x in (await client.get("/api/inbox/conversations", headers=owner_h)).json()}
    assert set(convs) == {"u9102", "u9103"}
    assert convs["u9102"]["lead"] is None and convs["u9103"]["lead"]["source"] == "instagram"
    # the same person asks later: now a lead
    body, h = signed({"object": "instagram", "entry": [{"id": "17841499999999999", "time": 2, "changes": [c("f4", "+", "9102")]}]})
    await client.post("/api/webhooks/meta", content=body, headers=h)
    convs = {x["contact"]["username"]: x for x in (await client.get("/api/inbox/conversations", headers=owner_h)).json()}
    assert convs["u9102"]["lead"] is not None
    s = (await client.get("/api/settings", headers=owner_h)).json()
    assert "цена" in s["ig_comment_lead_words"]
    assert (await client.put("/api/settings/ig_comment_lead_words", headers=owner_h, json={"value": "цена, +"})).status_code == 204


async def test_reaction_to_a_story_is_not_a_message_but_a_text_reply_is(client, db, owner_h, monkeypatch):
    from app.services import meta
    from tests.test_crm_inbox import ig_payload, signed

    async def no_profile(_):
        return None, None
    monkeypatch.setattr(meta, "ig_profile", no_profile)

    def story(sender, mid, text):
        p = ig_payload(sender, mid, text)
        p["entry"][0]["messaging"][0]["message"]["reply_to"] = {"story": {"id": "s1", "url": "https://example.com/s"}}
        return p

    body, h = signed(story("9201", "st.1", "❤️"))
    assert (await client.post("/api/webhooks/meta", content=body, headers=h)).json()["stored"] == 0
    assert (await client.get("/api/inbox/conversations", headers=owner_h)).json() == []
    body, h = signed(story("9201", "st.2", "Сколько стоит?"))
    assert (await client.post("/api/webhooks/meta", content=body, headers=h)).json()["stored"] == 1
    convs = (await client.get("/api/inbox/conversations", headers=owner_h)).json()
    assert len(convs) == 1 and convs[0]["lead"] is not None


async def test_whatsapp_through_360dialog_in_out_and_answers_from_the_phone(client, db, owner_h, monkeypatch):
    import json

    from app.core.config import get_settings
    from app.services import meta
    from tests.test_crm_inbox import wa_payload

    secret = "s" * 40
    monkeypatch.setattr(get_settings(), "wa_d360_api_key", "d360-key")
    monkeypatch.setattr(get_settings(), "wa_d360_webhook_secret", secret)
    url, jh = "/api/webhooks/360dialog", {"Content-Type": "application/json"}
    body = json.dumps(wa_payload("77011116060", "wamid.in1", "Здравствуйте, сколько стоит?"))
    assert (await client.post(url, content=body, headers=jh)).status_code == 401
    assert (await client.post(url, content=body, headers={**jh, "X-OE-Webhook-Secret": "wrong" * 8})).status_code == 401
    r = await client.post(url, content=body, headers={**jh, "X-OE-Webhook-Secret": secret})
    assert r.status_code == 200 and r.json()["stored"] == 1
    conv = (await client.get("/api/inbox/conversations", headers=owner_h)).json()[0]
    assert conv["channel"] == "whatsapp" and conv["lead"] is not None and conv["unread"] == 1

    sent = {}

    async def fake(url, token, payload):
        sent.update(url=url, token=token, payload=payload)
        return meta.SendResult(True, external_id="wamid.out1")
    monkeypatch.setattr(meta, "_post", fake)
    r = await client.post(f"/api/inbox/conversations/{conv['id']}/messages", headers=owner_h, json={"text": "Добрый день!"})
    assert r.status_code in (200, 201), r.text
    assert sent["url"] == "https://waba-v2.360dialog.io/messages" and sent["token"] == "d360-key"
    assert sent["payload"]["to"] == "77011116060" and sent["payload"]["text"]["body"] == "Добрый день!"

    # an answer typed in the WhatsApp Business app on the phone appears in the same chat, once
    echo = {"object": "whatsapp_business_account", "entry": [{"changes": [{"field": "smb_message_echoes", "value": {
        "message_echoes": [{"from": "77000000000", "to": "77011116060", "id": "wamid.echo1", "timestamp": "1795000000",
                            "type": "text", "text": {"body": "Ответ с телефона"}}]}}]}]}
    for _ in range(2):
        r = await client.post(url, content=json.dumps(echo), headers={**jh, "X-OE-Webhook-Secret": secret})
        assert r.status_code == 200
    msgs = (await client.get(f"/api/inbox/conversations/{conv['id']}/messages", headers=owner_h)).json()
    msgs = msgs["items"] if isinstance(msgs, dict) else msgs
    out = [m for m in msgs if m["direction"] == "out"]
    assert [m["text"] for m in out].count("Ответ с телефона") == 1 and len(out) == 2
    # Instagram payloads are not taken on this address
    r = await client.post(url, content=json.dumps({"object": "instagram", "entry": []}), headers={**jh, "X-OE-Webhook-Secret": secret})
    assert r.json()["stored"] == 0
