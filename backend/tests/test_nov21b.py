"""Owner's requests of 21.11.2026 (second batch): control of the work with leads."""
from datetime import timedelta

from sqlalchemy import select

from app import jobs
from app.models import Accrual, Conversation, Lead, LeadStage, Lesson, Notification, Room
from app.services.clock import now
from app.services.crm import stage_by_code
from tests.conftest import branch_id, level_id, login, make_staff
from tests.test_crm_inbox import ig_payload, signed

YANGI = "Янги шахар"


async def _trial(client, db, owner_h, sh, teacher, name, phone, tag):
    bid = await branch_id(db, YANGI)
    lead = (await client.post("/api/crm/leads", headers=sh, json={"full_name": name, "phone": phone, "branch_id": bid})).json()
    g = (await client.post("/api/groups", headers=owner_h, json={"name": tag, "branch_id": bid,
                                                                 "level_id": await level_id(db, "ELE"), "teacher_id": teacher.id})).json()
    room = await db.scalar(select(Room).where(Room.branch_id == bid))
    lesson = Lesson(branch_id=bid, group_id=g["id"], level_id=g["level_id"], teacher_id=teacher.id, room_id=room.id,
                    starts_at=now() + timedelta(minutes=30), ends_at=now() + timedelta(minutes=90))
    db.add(lesson)
    await db.flush()
    r = await client.post(f"/api/crm/leads/{lead['id']}/trial", headers=sh, json={"lesson_id": lesson.id, "notify": False})
    assert r.status_code == 200, r.text
    return lead["id"], lesson


async def test_no_show_reminds_the_manager_then_frees_the_lead_and_the_one_who_works_it_takes_it(client, db, owner_h):
    a = await make_staff(db, "sales", [YANGI], "+77052227001", "Менеджер А")
    b = await make_staff(db, "sales", [YANGI], "+77052227002", "Менеджер Б")
    teacher = await make_staff(db, "teacher", [YANGI], "+77052227003", "Учитель")
    await db.commit()
    ah, bh = await login(client, a.phone), await login(client, b.phone)
    lid, lesson = await _trial(client, db, owner_h, ah, teacher, "Не Пришёл", "+77052227004", "NS-1")
    assert (await jobs.lead_control(db))["noshow"] == 0  # the lesson is still ahead
    lesson.starts_at, lesson.ends_at = now() - timedelta(hours=3), now() - timedelta(hours=2)
    await db.flush()
    assert (await jobs.lead_control(db))["noshow"] == 1
    assert (await jobs.lead_control(db))["noshow"] == 0  # told once
    lead = await db.get(Lead, lid)
    await db.refresh(lead)
    assert lead.work_due_at is not None and lead.free_since is None
    titles = [n.title for n in await db.scalars(select(Notification).where(Notification.user_id == a.id))]
    assert any("не пришёл на пробный" in t for t in titles)
    # two hours passed and the manager did nothing: the lead is free, everyone is told
    lead.work_due_at = now() - timedelta(minutes=1)
    await db.flush()
    assert (await jobs.lead_control(db))["freed"] == 1
    await db.refresh(lead)
    assert lead.free_since is not None and lead.assignee_id == a.id
    assert any("Свободный лид" in n.title for n in await db.scalars(select(Notification).where(Notification.user_id == b.id)))
    card = (await client.get(f"/api/crm/leads/{lid}", headers=bh)).json()["lead"]
    assert card["free"] is True
    # B writes a note: the lead is his now
    r = await client.post(f"/api/crm/leads/{lid}/events", headers=bh, json={"kind": "note", "text": "Болел, запишем на среду"})
    assert r.status_code == 201, r.text
    card = (await client.get(f"/api/crm/leads/{lid}", headers=bh)).json()["lead"]
    assert card["free"] is False and card["assignee_id"] == b.id and card["last_note"] == "Болел, запишем на среду"
    assert (await jobs.lead_control(db))["freed"] == 0


async def test_after_the_trial_the_manager_has_an_hour_and_a_note_meets_the_deadline(client, db, owner_h):
    a = await make_staff(db, "sales", [YANGI], "+77052227011", "Менеджер А")
    teacher = await make_staff(db, "teacher", [YANGI], "+77052227012", "Учитель")
    await db.commit()
    ah, th = await login(client, a.phone), await login(client, teacher.phone)
    lid, lesson = await _trial(client, db, owner_h, ah, teacher, "Пришёл Сам", "+77052227013", "TD-1")
    lesson.starts_at = now() - timedelta(minutes=5)
    await db.flush()
    r = await client.put(f"/api/lessons/{lesson.id}/attendance", headers=th, json={"marks": [{"lead_id": lid, "status": "present"}]})
    assert r.status_code == 200, r.text
    lead = await db.get(Lead, lid)
    await db.refresh(lead)
    assert lead.work_due_at is not None and timedelta(minutes=50) < lead.work_due_at - now() < timedelta(minutes=61)
    await client.post(f"/api/crm/leads/{lid}/events", headers=ah, json={"kind": "call", "text": "Купит в пятницу"})
    await db.refresh(lead)
    assert lead.work_due_at is None and lead.free_since is None and lead.assignee_id == a.id


async def test_stage_deadline_is_set_in_the_dictionary_and_a_free_lead_is_seen_through_only_own(client, db, owner_h):
    bid = await branch_id(db, YANGI)
    a = await make_staff(db, "sales", [YANGI], "+77052227021", "Менеджер А")
    b = await make_staff(db, "sales", [YANGI], "+77052227022", "Менеджер Б")
    await db.commit()
    ah, bh = await login(client, a.phone), await login(client, b.phone)
    main = next(p for p in (await client.get("/api/crm/pipelines", headers=owner_h)).json() if p["code"] == "main")
    r = await client.post(f"/api/crm/pipelines/{main['id']}/stages", headers=owner_h, json={"name": "Начнут позже", "work_hours": 3})
    assert r.status_code == 201 and r.json()["work_hours"] == 3
    later = r.json()["id"]
    assert (await client.put("/api/crm/stage-access", headers=owner_h, json={"user_id": b.id, "stage_id": later, "level": "own"})).status_code == 204
    bh = await login(client, b.phone)
    lead = (await client.post("/api/crm/leads", headers=ah, json={"full_name": "Позже Начнёт", "phone": "+77052227023", "branch_id": bid})).json()
    assert (await client.post(f"/api/crm/leads/{lead['id']}/stage", headers=ah, json={"stage_id": later})).status_code == 200
    row = await db.get(Lead, lead["id"])
    await db.refresh(row)
    assert row.work_due_at is not None
    assert (await client.get(f"/api/crm/leads/{lead['id']}", headers=bh)).status_code == 404  # «Только свои»
    row.work_due_at = now() - timedelta(minutes=1)
    await db.flush()
    assert (await jobs.lead_control(db))["freed"] == 1
    assert (await client.get(f"/api/crm/leads/{lead['id']}", headers=bh)).json()["lead"]["free"] is True


async def test_idle_lead_without_a_note_or_a_task_pings_its_manager_once(client, db, owner_h, monkeypatch):
    monkeypatch.setattr(jobs, "_day_time", lambda t: True)
    bid = await branch_id(db, YANGI)
    a = await make_staff(db, "sales", [YANGI], "+77052227031", "Менеджер А")
    await db.commit()
    ah = await login(client, a.phone)
    quiet = (await client.post("/api/crm/leads", headers=ah, json={"full_name": "Тихий Лид", "phone": "+77052227032", "branch_id": bid})).json()
    noted = (await client.post("/api/crm/leads", headers=ah, json={"full_name": "С Заметкой", "phone": "+77052227033", "branch_id": bid})).json()
    await client.post(f"/api/crm/leads/{noted['id']}/events", headers=ah, json={"kind": "note", "text": "Думает"})
    assert (await jobs.lead_control(db))["idle"] == 0  # younger than 3 hours
    for lid in (quiet["id"], noted["id"]):
        row = await db.get(Lead, lid)
        row.created_at = row.stage_changed_at = now() - timedelta(hours=4)
    await db.flush()
    assert (await jobs.lead_control(db))["idle"] == 1
    assert (await jobs.lead_control(db))["idle"] == 0
    titles = [n.title for n in await db.scalars(select(Notification).where(Notification.user_id == a.id))]
    assert titles.count("Поработайте с лидом: Тихий Лид") == 1 and not any("С Заметкой" in t for t in titles)


async def test_client_message_goes_to_the_manager_who_answered_and_the_card_is_unanswered(client, db, owner_h):
    office = await make_staff(db, "office_manager", [YANGI], "+77052227041", "Офис Ответил")
    await db.commit()
    oh = await login(client, office.phone)
    body, h = signed(ig_payload("17841400000000777", "ig.b1", "Сколько стоит?"))
    await client.post("/api/webhooks/meta", content=body, headers=h)
    conv = await db.scalar(select(Conversation))
    lead = await db.scalar(select(Lead))
    board = (await client.get("/api/crm/board", headers=owner_h)).json()
    card = next(l for c in board["columns"] for l in c["leads"] if l["id"] == lead.id)
    assert card["unanswered"] is True
    r = await client.post(f"/api/inbox/conversations/{conv.id}/messages", headers=oh, json={"text": "Здравствуйте! 25 000"})
    assert r.status_code == 201, r.text
    await db.refresh(conv)
    assert conv.assignee_id == office.id
    card = (await client.get(f"/api/crm/leads/{lead.id}", headers=owner_h)).json()["lead"]
    assert card["unanswered"] is False
    msgs = (await client.get(f"/api/inbox/conversations/{conv.id}/messages", headers=owner_h)).json()
    assert msgs[-1]["sender_name"] == "Офис Ответил"
    before = len(list(await db.scalars(select(Notification).where(Notification.user_id == office.id, Notification.kind == "inbox"))))
    for i in (2, 3):  # every next message of the client comes to the one who answered
        body, h = signed(ig_payload("17841400000000777", f"ig.b{i}", f"А когда начало? {i}"))
        await client.post("/api/webhooks/meta", content=body, headers=h)
    after = len(list(await db.scalars(select(Notification).where(Notification.user_id == office.id, Notification.kind == "inbox"))))
    assert after - before == 2
    card = (await client.get(f"/api/crm/leads/{lead.id}", headers=owner_h)).json()["lead"]
    assert card["unanswered"] is True


async def test_sale_bonus_goes_to_the_manager_picked_at_the_payment(client, db, owner_h):
    sales = await make_staff(db, "sales", [YANGI], "+77052227051", "Продал")
    teacher = await make_staff(db, "teacher", [YANGI], "+77052227052", "Учитель")
    office = await make_staff(db, "office_manager", [YANGI], "+77052227053", "Принял Оплату")
    await db.commit()
    sh, th, oh = await login(client, sales.phone), await login(client, teacher.phone), await login(client, office.phone)
    lid, lesson = await _trial(client, db, owner_h, sh, teacher, "Купил Курс", "+77052227054", "SB-1")
    lesson.starts_at = now() - timedelta(minutes=5)
    await db.flush()
    await client.put(f"/api/lessons/{lesson.id}/attendance", headers=th, json={"marks": [{"lead_id": lid, "status": "present"}]})
    paid = await stage_by_code(db, "main", "paid")
    assert (await client.post(f"/api/crm/leads/{lid}/stage", headers=owner_h, json={"stage_id": paid.id})).status_code == 200
    sid = (await client.post(f"/api/crm/leads/{lid}/convert", headers=oh, json={})).json()["student_id"]
    await client.post(f"/api/groups/{lesson.group_id}/members", headers=oh, json={"student_id": sid})
    r = await client.post("/api/payments", headers=oh, json={"student_id": sid, "lessons": 8, "method": "kaspi", "seller_id": 999999})
    assert r.status_code == 400
    r = await client.post("/api/payments", headers=oh, json={"student_id": sid, "lessons": 8, "method": "kaspi", "seller_id": sales.id})
    assert r.status_code == 201 and r.json()["seller_id"] == sales.id
    sale = [x for x in await db.scalars(select(Accrual).where(Accrual.kind == "sale"))]
    assert len(sale) == 1 and sale[0].user_id == sales.id
    row = await db.get(Lead, lid)
    await db.refresh(row)
    assert (await db.get(LeadStage, row.stage_id)).code == "paid" and row.work_due_at is None


async def test_files_for_a_kind_of_users_are_accepted_once_and_kept_in_the_journal(client, db, owner_h):
    from app.services import files

    teacher = await make_staff(db, "teacher", [YANGI], "+77052227061", "Учитель Читает")
    sales = await make_staff(db, "sales", [YANGI], "+77052227062", "Продажник")
    await db.commit()
    th, sh = await login(client, teacher.phone), await login(client, sales.phone)
    auds = {a["code"] for a in (await client.get("/api/user-docs", headers=owner_h)).json()["audiences"]}
    assert {"teacher", "parent", "student"} <= auds
    keys = [files.save(b"%PDF-1.4 rules " + str(i).encode(), "application/pdf") for i in range(3)]
    for i in range(2):
        r = await client.post("/api/user-docs", headers=owner_h, json={"audience": "teacher", "title": f"Правила учителя {i}",
                                                                      "file_key": keys[i], "file_name": f"rules{i}.pdf"})
        assert r.status_code == 201, r.text
    r = await client.post("/api/user-docs", headers=owner_h, json={"audience": "teacher", "title": "Третий", "file_key": keys[2], "file_name": "x.pdf"})
    assert r.status_code == 400  # two files per kind of user
    assert (await client.post("/api/user-docs", headers=th, json={"audience": "teacher", "title": "Сам себе", "file_key": keys[2],
                                                                  "file_name": "x.pdf"})).status_code == 403
    mine = (await client.get("/api/user-docs/pending", headers=th)).json()
    assert len(mine) == 2 and mine[0]["url"].startswith("/api/files/")
    assert (await client.get("/api/user-docs/pending", headers=sh)).json() == []
    # somebody else's file can't be accepted
    assert (await client.post("/api/user-docs/accept", headers=sh, json={"doc_ids": [mine[0]["id"]]})).status_code == 204
    assert (await client.get("/api/user-docs/journal", headers=owner_h)).json() == []
    assert (await client.post("/api/user-docs/accept", headers=th, json={"doc_ids": [d["id"] for d in mine]})).status_code == 204
    assert (await client.post("/api/user-docs/accept", headers=th, json={"doc_ids": [d["id"] for d in mine]})).status_code == 204
    assert (await client.get("/api/user-docs/pending", headers=th)).json() == []  # asked once
    journal = (await client.get("/api/user-docs/journal", headers=owner_h)).json()
    assert len(journal) == 2 and journal[0]["user_name"] == "Учитель Читает" and journal[0]["audience_name"]
    assert (await client.delete(f"/api/user-docs/{mine[0]['id']}", headers=owner_h)).status_code == 204
    journal = (await client.get("/api/user-docs/journal", headers=owner_h)).json()
    assert len(journal) == 2 and sum(j["removed"] for j in journal) == 1
    assert [d["accepted"] for d in (await client.get("/api/user-docs", headers=owner_h)).json()["docs"]] == [1]


async def test_lesson_rating_by_qr_three_questions_and_only_admins_see_the_answers(client, db, owner_h):
    bid = await branch_id(db, YANGI)
    teacher = await make_staff(db, "teacher", [YANGI], "+77052227071", "Учитель Оценка")
    await db.commit()
    th = await login(client, teacher.phone)
    g = (await client.post("/api/groups", headers=owner_h, json={"name": "RATE-1", "branch_id": bid,
                                                                 "level_id": await level_id(db, "ELE"), "teacher_id": teacher.id})).json()
    assert (await client.post("/api/lesson-surveys", headers=th, json={"group_id": g["id"]})).status_code == 409  # no lesson yet
    room = await db.scalar(select(Room).where(Room.branch_id == bid))
    lesson = Lesson(branch_id=bid, group_id=g["id"], level_id=g["level_id"], teacher_id=teacher.id, room_id=room.id,
                    starts_at=now() - timedelta(minutes=40), ends_at=now() + timedelta(minutes=20))
    db.add(lesson)
    await db.flush()
    r = await client.post("/api/lesson-surveys", headers=th, json={"group_id": g["id"]})
    assert r.status_code == 200, r.text
    token = r.json()["token"]
    assert (await client.post("/api/lesson-surveys", headers=owner_h, json={"group_id": g["id"]})).json()["token"] == token
    pub = (await client.get(f"/api/public/lesson-survey/{token}")).json()
    assert pub["open"] and len(pub["questions"]) == 3 and pub["teacher"] == "Учитель Оценка"
    assert (await client.get("/api/public/lesson-survey/nope-nope-nope")).status_code == 404
    assert (await client.post(f"/api/public/lesson-survey/{token}", json={"answers": [5, 9, "x"]})).status_code == 400
    assert (await client.post(f"/api/public/lesson-survey/{token}", json={"answers": [5, 4, "Больше игр"]})).status_code == 201
    assert (await client.post(f"/api/public/lesson-survey/{token}", json={"answers": [3, 4, None]})).status_code == 201
    assert (await client.get("/api/lesson-surveys/results", headers=th)).status_code == 403  # the teacher never sees them
    res = (await client.get("/api/lesson-surveys/results", headers=owner_h)).json()
    row = res["lessons"][0]
    assert row["answers"] == 2 and row["avg"] == 4.0 and row["questions"][0]["avg"] == 4.0
    assert row["questions"][2]["comments"] == ["Больше игр"]
    assert res["teachers"][0]["teacher"] == "Учитель Оценка" and res["teachers"][0]["avg"] == 4.0
    # the admin changes the questions: new links get them, the old link keeps its own
    assert (await client.put("/api/lesson-surveys/questions", headers=th, json={"questions": [{"text": "Как урок?", "kind": "stars"}]})).status_code == 403
    r = await client.put("/api/lesson-surveys/questions", headers=owner_h, json={"questions": [{"text": "Как урок?", "kind": "stars"}]})
    assert r.status_code == 200 and len(r.json()) == 1
    assert len((await client.get(f"/api/public/lesson-survey/{token}")).json()["questions"]) == 3
