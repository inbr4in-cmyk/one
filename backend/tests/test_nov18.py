from datetime import timedelta

from sqlalchemy import func, select

from app.models import Lead, LeadStage
from app.services.clock import local, today
from tests.conftest import branch_id, login, make_staff

YANGI = "Янги шахар"


async def test_lead_history_names_every_step(client, db, owner_h, owner):
    bid = await branch_id(db, YANGI)
    lead = (await client.post("/api/crm/leads", headers=owner_h, json={"full_name": "Алия", "branch_id": bid})).json()
    await client.post(f"/api/crm/leads/{lead['id']}/events", headers=owner_h, json={"kind": "call", "text": "Позвонил, думает"})
    await client.patch(f"/api/crm/leads/{lead['id']}", headers=owner_h, json={"phone": "+77015550101"})
    card = (await client.get(f"/api/crm/leads/{lead['id']}", headers=owner_h)).json()
    texts = [e["text"] for e in card["events"]]
    assert "Изменено: телефон" in texts and "Позвонил, думает" in texts
    assert all(e["actor_name"] == owner.full_name for e in card["events"])
    assert card["lead"]["assignee_name"] == owner.full_name
    other = await make_staff(db, "sales", [YANGI], "+77080000779", "Новый Ответственный")
    await db.commit()
    r = await client.patch(f"/api/crm/leads/{lead['id']}", headers=owner_h, json={"assignee_id": other.id})
    assert r.json()["assignee_name"] == "Новый Ответственный"
    card = (await client.get(f"/api/crm/leads/{lead['id']}", headers=owner_h)).json()
    assert card["events"][0]["text"] == "Ответственный: Новый Ответственный" and card["events"][0]["actor_name"] == owner.full_name
    assert (await client.patch(f"/api/crm/leads/{lead['id']}", headers=owner_h, json={"assignee_id": 999999})).status_code == 400


async def test_lead_can_be_dated_back_a_month_at_most(client, db, owner_h):
    bid = await branch_id(db, YANGI)
    day = today() - timedelta(days=5)
    r = await client.post("/api/crm/leads", headers=owner_h, json={"full_name": "Вчерашний", "branch_id": bid,
                                                                  "contacted_on": day.isoformat()})
    assert r.status_code == 201
    lead = await db.get(Lead, r.json()["id"])
    await db.refresh(lead)
    assert local(lead.created_at).date() == day
    card = (await client.get(f"/api/crm/leads/{lead.id}", headers=owner_h)).json()
    assert f"дата обращения {day:%d.%m.%Y}" in card["events"][-1]["text"]
    assert local(__import__("datetime").datetime.fromisoformat(card["events"][-1]["at"])).date() == today()  # entered today
    for bad in (today() - timedelta(days=40), today() + timedelta(days=1)):
        r = await client.post("/api/crm/leads", headers=owner_h, json={"full_name": "Нельзя", "branch_id": bid,
                                                                      "contacted_on": bad.isoformat()})
        assert r.status_code == 400


async def test_admin_closes_funnel_stages_per_person(client, db, owner_h):
    bid = await branch_id(db, YANGI)
    sales = await make_staff(db, "sales", [YANGI], "+77080000777", "Менеджер Сауле")
    await db.commit()
    h = await login(client, sales.phone)
    lead = (await client.post("/api/crm/leads", headers=h, json={"full_name": "Тимур", "branch_id": bid})).json()
    new = await db.scalar(select(LeadStage).where(LeadStage.code == "new"))
    contacted = await db.scalar(select(LeadStage).where(LeadStage.code == "contacted"))
    table = (await client.get("/api/crm/stage-access", headers=owner_h)).json()
    assert any(u["id"] == sales.id and u["can_edit"] for u in table["users"]) and table["cells"] == {}
    assert (await client.get("/api/crm/stage-access", headers=h)).status_code == 403  # only who manages roles

    # view only: the card opens, nothing can be changed
    r = await client.put("/api/crm/stage-access", headers=owner_h, json={"user_id": sales.id, "stage_id": new.id, "level": "view"})
    assert r.status_code == 204
    card = (await client.get(f"/api/crm/leads/{lead['id']}", headers=h)).json()
    assert card["lead"]["can_edit"] is False
    assert (await client.patch(f"/api/crm/leads/{lead['id']}", headers=h, json={"notes": "x"})).status_code == 403
    assert (await client.post(f"/api/crm/leads/{lead['id']}/stage", headers=h, json={"stage_id": contacted.id})).status_code == 403

    # hidden: no column, no card
    await client.put("/api/crm/stage-access", headers=owner_h, json={"user_id": sales.id, "stage_id": new.id, "level": "none"})
    cols = (await client.get("/api/crm/board", headers=h)).json()["columns"]
    assert new.id not in {c["stage"]["id"] for c in cols}
    assert (await client.get(f"/api/crm/leads/{lead['id']}", headers=h)).status_code == 404
    assert new.id in {c["stage"]["id"] for c in (await client.get("/api/crm/board", headers=owner_h)).json()["columns"]}

    # only own: other people's leads on that stage are not shown, own ones stay editable
    other = (await client.post("/api/crm/leads", headers=owner_h, json={"full_name": "Чужой", "branch_id": bid})).json()
    await client.put("/api/crm/stage-access", headers=owner_h, json={"user_id": sales.id, "stage_id": new.id, "level": "own"})
    col = next(c for c in (await client.get("/api/crm/board", headers=h)).json()["columns"] if c["stage"]["id"] == new.id)
    assert {x["id"] for x in col["leads"]} == {lead["id"]} and col["total"] == 1
    assert (await client.get(f"/api/crm/leads/{other['id']}", headers=h)).status_code == 404
    assert (await client.patch(f"/api/crm/leads/{lead['id']}", headers=h, json={"notes": "моё"})).status_code == 200

    # back to what the role gives
    await client.put("/api/crm/stage-access", headers=owner_h, json={"user_id": sales.id, "stage_id": new.id, "level": "edit"})
    assert (await client.get("/api/crm/stage-access", headers=owner_h)).json()["cells"] == {}
    assert (await client.patch(f"/api/crm/leads/{lead['id']}", headers=h, json={"notes": "x"})).status_code == 200


async def test_instagram_lead_has_no_branch_until_staff_pick_it(client, db, owner_h, monkeypatch):
    from app.services import meta
    from tests.test_crm_inbox import ig_payload, signed

    async def nobody(user_id):
        return None, None

    monkeypatch.setattr(meta, "ig_profile", nobody)
    bid = await branch_id(db, YANGI)
    sales = await make_staff(db, "sales", [YANGI], "+77080000778", "Менеджер филиала")
    await db.commit()
    h = await login(client, sales.phone)
    body, hd = signed(ig_payload("17841400000000091", "ig.b1", "Здравствуйте"))
    await client.post("/api/webhooks/meta", content=body, headers=hd)
    conv = (await client.get("/api/inbox/conversations", headers=h)).json()[0]  # a branch manager sees it too
    assert conv["branch_id"] is None
    lead_id = conv["lead"]["id"]
    card = (await client.get(f"/api/crm/leads/{lead_id}", headers=h)).json()["lead"]
    assert card["branch_id"] is None
    cols = (await client.get(f"/api/crm/board?branch_id={bid}", headers=h)).json()["columns"]
    assert any(x["id"] == lead_id for c in cols for x in c["leads"])
    assert (await client.post(f"/api/crm/leads/{lead_id}/convert", headers=owner_h, json={})).status_code == 400
    r = await client.patch(f"/api/crm/leads/{lead_id}", headers=h, json={"branch_id": bid})
    assert r.status_code == 200 and r.json()["branch_id"] == bid
    assert (await client.get(f"/api/inbox/conversations/{conv['id']}", headers=h)).json()["branch_id"] == bid
    events = (await client.get(f"/api/crm/leads/{lead_id}", headers=h)).json()["events"]
    assert any(e["text"] == f"Филиал: {YANGI}" and e["actor_name"] == "Менеджер филиала" for e in events)


async def test_schedule_change_keeps_the_old_one_and_never_leaves_a_group_empty(client, db, owner_h):
    from app.models import Lesson, Room
    from app.services.clock import at_local
    from tests.test_core_learning import _setup
    from tests.conftest import level_id
    import datetime as dt

    bid, teacher, room, g = await _setup(db, client, owner_h)
    r = await client.post(f"/api/groups/{g['id']}/schedule", headers=owner_h, json={
        "weekdays": [0, 2, 4], "start_time": "16:00", "end_time": "17:30", "room_id": room.id, "valid_from": today().isoformat()})
    rule_id, before = r.json()["rule_id"], r.json()["created"]
    day = today() + timedelta(days=14)
    # a teacher cannot change it: admin and branch admin only
    h = await login(client, teacher.phone)
    new = {"weekdays": [1, 3], "start_time": "18:00", "end_time": "19:30", "room_id": room.id, "valid_from": day.isoformat()}
    assert (await client.post(f"/api/schedule-rules/{rule_id}/change", headers=h, json=new)).status_code == 403

    # another group already sits in that room on the new days → nothing changes at all
    other = (await client.post("/api/groups", headers=owner_h, json={
        "name": "BUSY", "branch_id": bid, "level_id": await level_id(db, "ELE"), "teacher_id": teacher.id, "room_id": room.id,
        "capacity": 12})).json()
    await client.post(f"/api/groups/{other['id']}/schedule", headers=owner_h, json={
        "weekdays": [1], "start_time": "18:30", "end_time": "19:30", "room_id": room.id, "valid_from": today().isoformat()})
    r = await client.post(f"/api/schedule-rules/{rule_id}/change", headers=owner_h, json=new)
    assert r.status_code == 409 and "не изменено" in r.json()["detail"]
    grp = (await client.get(f"/api/groups/{g['id']}", headers=owner_h)).json()
    assert [x["id"] for x in grp["schedule"]] == [rule_id] and grp["schedule"][0]["valid_to"] is None and grp["old_schedule"] == []
    planned = select(func.count()).select_from(Lesson).where(Lesson.group_id == g["id"], Lesson.status == "planned")
    assert await db.scalar(planned) == before

    # free days: the old schedule ends the day before, its later lessons are replaced by the new ones
    new["weekdays"] = [3, 5]
    r = await client.post(f"/api/schedule-rules/{rule_id}/change", headers=owner_h, json=new)
    assert r.status_code == 200, r.text
    assert r.json()["created"] > 0 and r.json()["replaced"] > 0
    grp = (await client.get(f"/api/groups/{g['id']}", headers=owner_h)).json()
    assert len(grp["schedule"]) == 2  # the old one runs until the day before, the new one from that day
    old, cur = grp["schedule"]
    assert old["id"] == rule_id and old["valid_to"] == (day - timedelta(days=1)).isoformat()
    assert cur["valid_from"] == day.isoformat() and cur["weekdays"] == [3, 5] and cur["start"] == "18:00"
    cut = at_local(day, dt.time(0))
    for l in await db.scalars(select(Lesson).where(Lesson.group_id == g["id"], Lesson.status == "planned")):
        assert (l.rule_id == rule_id) == (l.starts_at < cut)


async def test_waiting_for_a_group_status(client, db, owner_h):
    from tests.test_core_learning import _setup, _student

    bid, teacher, room, g = await _setup(db, client, owner_h)
    s = await _student(db, client, owner_h, bid)
    r = await client.patch(f"/api/students/{s['id']}", headers=owner_h, json={"status": "waiting"})
    assert r.status_code == 200 and r.json()["status"] == "waiting"
    # a freeze works without a payment and without a group, and ends back in «ждёт группу»
    r = await client.post(f"/api/students/{s['id']}/freeze", headers=owner_h,
                          json={"starts_on": str(today()), "ends_on": str(today() + timedelta(days=7))})
    assert r.status_code == 200 and r.json()["status"] == "frozen"
    r = await client.post(f"/api/students/{s['id']}/unfreeze", headers=owner_h)
    assert r.json()["status"] == "waiting"
    # joins a group → studies; with a group the status cannot be set
    r = await client.post(f"/api/groups/{g['id']}/members", headers=owner_h, json={"student_id": s["id"]})
    assert r.status_code in (200, 201), r.text
    assert (await client.get(f"/api/students/{s['id']}", headers=owner_h)).json()["status"] == "active"
    r = await client.patch(f"/api/students/{s['id']}", headers=owner_h, json={"status": "waiting"})
    assert r.status_code == 400 and "есть группа" in r.json()["detail"]


async def test_room_with_its_own_teacher_pay_is_flat_and_cannot_be_deleted(client, db, owner_h):
    from app.models import Accrual
    from tests.test_core_learning import _lesson_now, _setup, _student

    bid, teacher, room, g = await _setup(db, client, owner_h)
    await db.refresh(room)
    body = {"name": room.name, "capacity": room.capacity, "equipment": None, "status": "active"}
    room_id = room.id
    # a branch admin cannot set the special pay: his save leaves it as it was
    admin = await make_staff(db, "branch_admin", [YANGI], "+77030000555")
    ah = await login(client, admin.phone)
    r = await client.patch(f"/api/rooms/{room_id}", headers=ah, json={**body, "teacher_rate": 9000})
    assert r.status_code == 200 and r.json()["teacher_rate"] is None
    r = await client.patch(f"/api/rooms/{room_id}", headers=owner_h, json={**body, "teacher_rate": 3500})
    assert r.status_code == 200 and r.json()["teacher_rate"] == 3500
    await db.refresh(room)  # the test shares one session with the app
    assert (await client.patch(f"/api/rooms/{room_id}", headers=ah, json=body)).json()["teacher_rate"] == 3500
    # nobody deletes such a room
    for h in (ah, owner_h):
        assert (await client.post(f"/api/rooms/{room_id}/archive", headers=h, json={})).status_code == 409
    ids = []
    for i in range(8):
        s = await _student(db, client, owner_h, bid, f"Шу {i}", f"+7705111330{i}")
        await client.post(f"/api/groups/{g['id']}/members", headers=owner_h, json={"student_id": s["id"]})
        ids.append(s["id"])
    lesson = await _lesson_now(db, g, teacher, room)
    th = await login(client, teacher.phone)
    r = await client.put(f"/api/lessons/{lesson.id}/attendance", headers=th,
                         json={"marks": [{"student_id": i, "status": "present"} for i in ids]})
    assert r.status_code == 200, r.text
    acc = await db.scalar(select(Accrual).where(Accrual.kind == "lesson", Accrual.ref_id == lesson.id))
    assert acc.amount == 3500  # 8 students, still no extra for the 6th–8th
