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

    assert await pay("excused") == 0      # asked off, the first time this month: the lesson stays, no pay
    assert await pay("present") == 2000
    assert await pay("absent") == 1000    # no warning: the lesson is taken, the teacher gets the no-show rate


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


async def test_schedule_of_a_working_group_is_changed_from_a_past_day(client, db, owner_h):
    from app.models.learning import LessonStatus
    from app.services.clock import now
    from tests.test_core_learning import _setup, _student

    bid, teacher, room, g = await _setup(db, client, owner_h)
    start = today() - timedelta(days=10)
    daily = {"weekdays": list(range(7)), "room_id": room.id}
    r = await client.post(f"/api/groups/{g['id']}/schedule", headers=owner_h,
                          json={**daily, "start_time": "07:00", "end_time": "07:30", "valid_from": start.isoformat()})
    assert r.status_code == 201, r.text
    rule_id = r.json()["rule_id"]
    s = await _student(db, client, owner_h, bid, "Смена Расписания", "+77051116070")
    await client.post(f"/api/groups/{g['id']}/members", headers=owner_h, json={"student_id": s["id"], "joined_on": start.isoformat()})
    lessons = list(await db.scalars(select(Lesson).where(Lesson.group_id == g["id"]).order_by(Lesson.starts_at)))
    since = today() - timedelta(days=5)
    marked = next(x for x in lessons if local(x.starts_at).date() == since + timedelta(days=1))
    r = await client.put(f"/api/lessons/{marked.id}/attendance", headers=owner_h,
                         json={"marks": [{"student_id": s["id"], "status": "present"}], "reason": "внесено позже"})
    assert r.status_code == 200, r.text

    ch = f"/api/schedule-rules/{rule_id}/change"
    new = {**daily, "start_time": "08:00", "end_time": "08:30"}
    old = (today() - timedelta(days=40)).isoformat()
    assert (await client.post(ch, headers=owner_h, json={**new, "valid_from": old})).status_code == 400
    r = await client.post(ch, headers=owner_h, json={**new, "valid_from": since.isoformat()})
    assert r.status_code == 200, r.text
    assert r.json()["past"] == 4  # five past days by the new time, minus the day already held
    db.expire_all()
    rows = list(await db.scalars(select(Lesson).where(Lesson.group_id == g["id"]).order_by(Lesson.starts_at)))
    live = [x for x in rows if x.status != LessonStatus.CANCELLED]
    by_day = {}
    for x in live:
        by_day.setdefault(local(x.starts_at).date(), []).append(local(x.starts_at).hour)
    assert by_day[since - timedelta(days=1)] == [7]            # before the change: the old time
    assert by_day[since] == [8]                                # from the change: the new time, the old lesson is cancelled
    assert by_day[since + timedelta(days=1)] == [7]            # the held lesson is kept, no second lesson that day
    assert all(h == [8] for d, h in by_day.items() if d >= today())
    kept = await db.get(Lesson, marked.id)
    assert kept.status == LessonStatus.DONE and kept.attendance_marked_at is not None


async def test_one_lesson_is_moved_to_another_time_and_a_free_room(client, db, owner_h):
    from app.models import Attendance, Room
    from app.models.learning import LessonStatus
    from app.services.clock import at_local
    from datetime import time
    from tests.test_core_learning import _setup, _student

    bid, teacher, room, g = await _setup(db, client, owner_h)
    rooms = (await db.scalars(select(Room).where(Room.branch_id == bid).order_by(Room.id))).all()
    other = next(x for x in rooms if x.id != room.id)
    s = await _student(db, client, owner_h, bid, "Перенос Урока", "+77051116080")
    await client.post(f"/api/groups/{g['id']}/members", headers=owner_h,
                      json={"student_id": s["id"], "joined_on": (today() - timedelta(days=5)).isoformat()})
    day = today() + timedelta(days=2)
    a = Lesson(branch_id=bid, group_id=g["id"], level_id=g["level_id"], teacher_id=teacher.id, room_id=room.id,
               starts_at=at_local(day, time(9, 0)), ends_at=at_local(day, time(10, 20)))
    # another group's lesson holds the same room at 11:00
    b = Lesson(branch_id=bid, teacher_id=(await make_staff(db, "teacher", [YANGI], "+77051116081", "Другой")).id, room_id=room.id,
               student_id=s["id"], starts_at=at_local(day, time(11, 0)), ends_at=at_local(day, time(12, 0)))
    db.add_all([a, b])
    await db.flush()
    aid = a.id
    new = {"starts_at": at_local(day, time(11, 0)).isoformat(), "ends_at": at_local(day, time(12, 20)).isoformat()}
    o = (await client.get(f"/api/lessons/{aid}/move-options", headers=owner_h, params=new)).json()
    assert o == {"busy_room_ids": [room.id], "teacher_busy": False}
    r = await client.post(f"/api/lessons/{aid}/move", headers=owner_h, json={**new, "room_id": room.id})
    assert r.status_code == 409 and "занят" in r.json()["detail"]
    r = await client.post(f"/api/lessons/{aid}/move", headers=owner_h, json={**new, "room_id": other.id})  # no reason needed
    assert r.status_code == 200, r.text
    moved = r.json()
    assert moved["room_id"] == other.id and moved["id"] != aid
    await db.refresh(a)
    assert a.status == LessonStatus.CANCELLED and a.cancel_reason == "Перенос"

    # a lesson already held: same lesson, marks and pay stay, only time and room change
    past_day = today() - timedelta(days=1)
    if past_day.month != today().month:
        past_day = today()
    h = Lesson(branch_id=bid, group_id=g["id"], level_id=g["level_id"], teacher_id=teacher.id, room_id=room.id,
               starts_at=at_local(past_day, time(3, 0)), ends_at=at_local(past_day, time(3, 30)))
    db.add(h)
    await db.flush()
    hid = h.id
    r = await client.put(f"/api/lessons/{hid}/attendance", headers=owner_h,
                         json={"marks": [{"student_id": s["id"], "status": "present"}], "reason": "внесено позже"})
    assert r.status_code == 200, r.text
    r = await client.post(f"/api/lessons/{hid}/move", headers=owner_h, json={
        "starts_at": at_local(past_day, time(4, 0)).isoformat(), "ends_at": at_local(past_day, time(4, 30)).isoformat(), "room_id": other.id})
    assert r.status_code == 200, r.text
    assert r.json()["id"] == hid and r.json()["room_id"] == other.id and r.json()["status"] == "done"
    assert await db.scalar(select(Attendance.id).where(Attendance.lesson_id == hid)) is not None
    far = today() + timedelta(days=40)
    r = await client.post(f"/api/lessons/{hid}/move", headers=owner_h, json={
        "starts_at": at_local(far, time(4, 0)).isoformat(), "ends_at": at_local(far, time(4, 30)).isoformat()})
    assert r.status_code == 400


async def test_admin_deletes_a_mistaken_payment_completely(client, db, owner_h):
    from app.models import BookStock, Payment, Refund, Student
    from tests.conftest import login
    from tests.test_core_learning import _setup, _student

    bid, teacher, room, g = await _setup(db, client, owner_h)
    s = await _student(db, client, owner_h, bid, "Ошибочная Оплата", "+77051116090")
    sid = s["id"]
    manager = await make_staff(db, "office_manager", [YANGI], "+77051116091", "Менеджер")
    await db.commit()
    mh = await login(client, manager.phone)

    async def state():
        st = await db.get(Student, sid)
        await db.refresh(st)
        return st.lessons_paid, st.lessons_left, st.money_balance

    p1 = (await client.post("/api/payments", headers=mh, json={"student_id": sid, "amount": 33500, "method": "kaspi"})).json()
    assert await state() == (11, 11, 500)
    r = await client.post(f"/api/payments/{p1['id']}/refund", headers=owner_h, json={"lessons": 2, "amount": 6000, "reason": "ошибка"})
    assert r.status_code == 201, r.text
    assert await state() == (9, 9, 500)
    assert (await client.delete(f"/api/payments/{p1['id']}", headers=mh)).status_code == 403  # managers cannot
    r = await client.delete(f"/api/payments/{p1['id']}", headers=owner_h)
    assert r.status_code == 200, r.text
    assert await state() == (0, 0, 0)
    assert await db.scalar(select(Payment.id).where(Payment.student_id == sid)) is None
    assert await db.scalar(select(Refund.id).where(Refund.payment_id == p1["id"])) is None
    assert (await client.get("/api/payments", headers=owner_h, params={"student_id": sid})).json()["items"] == []

    # a book taken «из оплаты»: the course payment is protected until the book payment is deleted; the book returns to stock
    p2 = (await client.post("/api/payments", headers=owner_h, json={"student_id": sid, "amount": 33000, "method": "cash"})).json()
    b = (await client.post("/api/books", headers=owner_h, json={
        "title": "Delete SB", "level_id": await level_id(db, "ELE"), "sale_price": 4000, "purchase_price": 2500})).json()
    await client.post("/api/books/receive", headers=owner_h, json={"branch_id": bid, "book_id": b["id"], "qty": 5, "unit_price": 2500})
    sale = (await client.post("/api/books/sell", headers=owner_h, json={"student_id": sid, "book_id": b["id"], "from_payment": True})).json()
    assert (await client.delete(f"/api/payments/{p2['id']}", headers=owner_h)).status_code == 409
    assert (await client.delete(f"/api/payments/{sale['payment_id']}", headers=owner_h)).status_code == 200
    src = await db.get(Payment, p2["id"])
    await db.refresh(src)
    st = await db.get(Student, sid)
    await db.refresh(st)
    assert src.amount == 33000 and src.lesson_price == 3000 and st.balance_lesson_price == 3000
    stock = await db.scalar(select(BookStock).where(BookStock.book_id == b["id"], BookStock.branch_id == bid))
    await db.refresh(stock)
    assert stock.qty == 5
    assert (await client.delete(f"/api/payments/{p2['id']}", headers=owner_h)).status_code == 200
    assert await state() == (0, 0, 0)


async def test_finished_group_goes_to_the_archive_and_lets_its_students_go(client, db, owner_h):
    from tests.test_core_learning import _setup, _student

    bid, teacher, room, g = await _setup(db, client, owner_h)
    s = await _student(db, client, owner_h, bid, "Закончил Курс", "+77051116095")
    await client.post(f"/api/groups/{g['id']}/members", headers=owner_h, json={"student_id": s["id"]})
    await client.post(f"/api/groups/{g['id']}/schedule", headers=owner_h,
                      json={"weekdays": list(range(7)), "start_time": "07:00", "end_time": "07:30", "room_id": room.id})
    assert (await client.post(f"/api/groups/{g['id']}/archive", headers=owner_h)).status_code == 204
    m = await db.scalar(select(GroupMember).where(GroupMember.group_id == g["id"]))
    await db.refresh(m)
    assert m.left_on == today()
    from app.models.learning import LessonStatus
    from app.services.clock import now
    assert await db.scalar(select(Lesson.id).where(Lesson.group_id == g["id"], Lesson.starts_at > now(),
                                                   Lesson.status == LessonStatus.PLANNED)) is None
    await client.post("/api/payments", headers=owner_h, json={"student_id": s["id"], "lessons": 4, "method": "cash"})
    rows = (await client.get("/api/payments", headers=owner_h, params={"student_id": s["id"], "category": "book"})).json()
    assert rows["items"] == []
    rows = (await client.get("/api/payments", headers=owner_h, params={"student_id": s["id"], "category": "course"})).json()
    assert len(rows["items"]) == 1
