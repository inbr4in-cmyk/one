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


async def test_student_is_moved_to_another_branch_without_a_group(client, db, owner_h):
    from tests.test_core_learning import _student

    bid, north = await branch_id(db, YANGI), await branch_id(db, "Север")
    teacher = await make_staff(db, "teacher", [YANGI], "+77052227081", "Учитель")
    g = (await client.post("/api/groups", headers=owner_h, json={"name": "BR-1", "branch_id": bid,
                                                                 "level_id": await level_id(db, "ELE"), "teacher_id": teacher.id})).json()
    sid = (await _student(db, client, owner_h, bid, "Переезд Филиал", "+77052227082"))["id"]
    await client.post(f"/api/groups/{g['id']}/members", headers=owner_h, json={"student_id": sid})
    await client.post("/api/payments", headers=owner_h, json={"student_id": sid, "lessons": 8, "method": "cash", "level_id": await level_id(db, "ELE")})
    before = (await client.get(f"/api/students/{sid}", headers=owner_h)).json()
    assert (await client.post(f"/api/students/{sid}/branch", headers=owner_h, json={"branch_id": bid, "reason": "тот же"})).status_code == 400
    r = await client.post(f"/api/students/{sid}/branch", headers=owner_h, json={"branch_id": north, "reason": "Переехали ближе к Северу"})
    assert r.status_code == 200, r.text
    after = r.json()
    assert after["branch_id"] == north and after["lessons_left"] == before["lessons_left"] and after["status"] == "waiting"
    assert all(x["left_on"] for x in after["groups"])
    hist = (await client.get(f"/api/students/{sid}/history", headers=owner_h)).json()
    assert any(h["kind"] == "branch" and "Север" in h["text"] for h in hist)


async def test_paid_lead_without_a_group_for_an_hour_alerts_the_branch_admin(client, db, owner_h):
    bid = await branch_id(db, YANGI)
    admin = await make_staff(db, "branch_admin", [YANGI], "+77052227091", "Админ Филиала")
    teacher = await make_staff(db, "teacher", [YANGI], "+77052227092", "Учитель")
    await db.commit()
    lead = (await client.post("/api/crm/leads", headers=owner_h, json={"full_name": "Оплатил Безгруппы", "phone": "+77052227093", "branch_id": bid})).json()
    paid = await stage_by_code(db, "main", "paid")
    assert (await client.post(f"/api/crm/leads/{lead['id']}/stage", headers=owner_h, json={"stage_id": paid.id})).status_code == 200
    sid = (await client.post(f"/api/crm/leads/{lead['id']}/convert", headers=owner_h, json={})).json()["student_id"]
    assert (await jobs.lead_control(db))["paid_no_group"] == 0  # the hour has not passed
    row = await db.get(Lead, lead["id"])
    row.stage_changed_at = now() - timedelta(hours=2)
    await db.flush()
    assert (await jobs.lead_control(db))["paid_no_group"] == 1
    assert (await jobs.lead_control(db))["paid_no_group"] == 0  # once a day
    titles = [n.title for n in await db.scalars(select(Notification).where(Notification.user_id == admin.id))]
    assert "Оплатил Безгруппы оплатил, но ещё не в группе" in titles
    # in a group: nothing more to remind about
    g = (await client.post("/api/groups", headers=owner_h, json={"name": "PG-1", "branch_id": bid,
                                                                 "level_id": await level_id(db, "ELE"), "teacher_id": teacher.id})).json()
    assert (await client.post(f"/api/groups/{g['id']}/members", headers=owner_h, json={"student_id": sid})).status_code in (200, 201)
    from app.core.kv import get_kv
    await get_kv().delete(f"once:paid-no-group:{lead['id']}:{__import__('app.services.clock', fromlist=['local']).local(now()).date()}")
    assert (await jobs.lead_control(db))["paid_no_group"] == 0


async def test_member_since_is_corrected_and_the_student_appears_in_past_lessons(client, db, owner_h):
    from app.models import GroupMember
    from app.services.clock import today
    from tests.test_core_learning import _student

    bid = await branch_id(db, YANGI)
    teacher = await make_staff(db, "teacher", [YANGI], "+77052227091", "Учитель")
    g = (await client.post("/api/groups", headers=owner_h, json={"name": "MS-1", "branch_id": bid,
                                                                 "level_id": await level_id(db, "ELE"), "teacher_id": teacher.id})).json()
    sid = (await _student(db, client, owner_h, bid, "Дата Группы", "+77052227092"))["id"]
    await client.post(f"/api/groups/{g['id']}/members", headers=owner_h, json={"student_id": sid})
    url = f"/api/groups/{g['id']}/members/{sid}"
    back = today() - timedelta(days=10)
    assert (await client.patch(url, headers=owner_h, json={"joined_on": (today() - timedelta(days=40)).isoformat()})).status_code == 400
    assert (await client.patch(url, headers=owner_h, json={"joined_on": (today() + timedelta(days=1)).isoformat()})).status_code == 400
    r = await client.patch(url, headers=owner_h, json={"joined_on": back.isoformat()})
    assert r.status_code == 200, r.text
    m = await db.scalar(select(GroupMember).where(GroupMember.student_id == sid))
    await db.refresh(m)
    assert m.joined_on == back
    rows = (await client.get(f"/api/groups/{g['id']}/members", headers=owner_h)).json()
    assert rows[0]["joined_on"] == back.isoformat()
    note = await db.scalar(select(Notification).where(Notification.user_id == teacher.id, Notification.kind == "attendance"))
    assert note is None  # no lessons were held in those days: nothing to fill in
    room = await db.scalar(select(Room).where(Room.branch_id == bid))
    db.add(Lesson(group_id=g["id"], branch_id=bid, teacher_id=teacher.id, room_id=room.id,
                  starts_at=now() - timedelta(days=12), ends_at=now() - timedelta(days=12) + timedelta(hours=1)))
    await db.commit()
    assert (await client.patch(url, headers=owner_h, json={"joined_on": (today() - timedelta(days=15)).isoformat()})).status_code == 200
    note = await db.scalar(select(Notification).where(Notification.user_id == teacher.id, Notification.kind == "attendance"))
    assert note is not None and "MS-1" in note.title and note.link == f"/groups/{g['id']}"


async def test_payments_excel_by_filter_and_old_finished_groups_are_closed(client, db, owner_h):
    import io

    from openpyxl import load_workbook

    from app.models import Group, GroupMember, ScheduleRule
    from app.services.clock import today
    from tests.test_core_learning import _student

    bid = await branch_id(db, YANGI)
    teacher = await make_staff(db, "teacher", [YANGI], "+77052227095", "Учитель")
    lvl = await level_id(db, "ELE")
    g = (await client.post("/api/groups", headers=owner_h, json={"name": "FX-1", "branch_id": bid, "level_id": lvl, "teacher_id": teacher.id})).json()
    sid = (await _student(db, client, owner_h, bid, "Эксель Оплата", "+77052227096"))["id"]
    await client.post(f"/api/groups/{g['id']}/members", headers=owner_h, json={"student_id": sid})
    await client.post("/api/payments", headers=owner_h, json={"student_id": sid, "lessons": 8, "method": "cash", "level_id": lvl})
    d = today().isoformat()
    r = await client.get(f"/api/payments-export.xlsx?date_from={d}&date_to={d}&category=course", headers=owner_h)
    assert r.status_code == 200, r.text
    ws = load_workbook(io.BytesIO(r.content)).active
    assert ws.cell(1, 13).value == "Продал" and any(row[2] == "Эксель Оплата" for row in ws.iter_rows(min_row=2, values_only=True))
    r = await client.get(f"/api/payments-export.xlsx?date_from={d}&date_to={d}&category=book", headers=owner_h)
    assert not any(row[2] == "Эксель Оплата" for row in load_workbook(io.BytesIO(r.content)).active.iter_rows(min_row=2, values_only=True))
    th = await login(client, "+77052227095")
    assert (await client.get("/api/payments-export.xlsx", headers=th)).status_code == 403

    # a group finished the old way: archived, but its lessons and members were left behind
    room = await db.scalar(select(Room).where(Room.branch_id == bid))
    grp = await db.get(Group, g["id"])
    grp.archived_at = now() - timedelta(days=2)
    db.add(Lesson(group_id=grp.id, branch_id=bid, level_id=lvl, teacher_id=teacher.id, room_id=room.id,
                  starts_at=now() + timedelta(days=1), ends_at=now() + timedelta(days=1, hours=1)))
    await db.commit()
    pre = await jobs.close_finished_groups(db, commit=False)
    assert pre["lessons"] == 1 and pre["members"] == 1
    assert await db.scalar(select(GroupMember.left_on).where(GroupMember.group_id == grp.id)) is None
    await jobs.close_finished_groups(db, commit=True)
    assert await db.scalar(select(GroupMember.left_on).where(GroupMember.group_id == grp.id)) is not None
    assert (await jobs.close_finished_groups(db, commit=False))["groups"] == []


async def test_course_with_its_own_teacher_rate_pays_it_in_any_format_and_salary_page_splits_rate_and_kpi(client, db, owner_h):
    from app.models import Level
    from app.services.clock import period_of, today
    from tests.test_core_learning import _lesson_now, _setup, _student

    bid, teacher, room, g = await _setup(db, client, owner_h)
    ids, teacher_id, room_id = [], teacher.id, room.id
    for i in range(7):
        s = await _student(db, client, owner_h, bid, f"Ставка {i}", f"+7705222810{i}")
        await client.post(f"/api/groups/{g['id']}/members", headers=owner_h, json={"student_id": s["id"]})
        ids.append(s["id"])
    marks = {"marks": [{"student_id": sid, "status": "present"} for sid in ids]}
    l1 = (await _lesson_now(db, g, teacher, room)).id
    await db.commit()
    assert (await client.put(f"/api/lessons/{l1}/attendance", headers=owner_h, json=marks)).status_code == 200
    p = (await client.get(f"/api/payroll/person?user_id={teacher_id}&period={period_of(today())}", headers=owner_h)).json()
    assert (p["rate_total"], p["kpi_total"], p["lessons_total"]) == (2500, 200, 2700)
    assert p["groups"][0]["lessons"][0]["base"] == 2500 and p["groups"][0]["lessons"][0]["kpi"] == 200

    lv = await db.get(Level, g["level_id"])
    await db.refresh(lv)
    body = {"name": lv.name, "color": lv.color, "lesson_price": lv.lesson_price, "track": lv.track, "order": lv.order,
            "duration_months": lv.duration_months, "next_level_id": lv.next_level_id}
    r = await client.patch(f"/api/levels/{g['level_id']}", headers=owner_h, json={**body, "teacher_rate": 5000})
    assert r.status_code == 200 and r.json()["teacher_rate"] == 5000
    assert (await client.patch(f"/api/levels/{g['level_id']}", headers=owner_h, json=body)).json()["teacher_rate"] == 5000  # kept
    l2 = Lesson(branch_id=g["branch_id"], group_id=g["id"], level_id=g["level_id"], teacher_id=teacher_id, room_id=room_id,
                starts_at=now() - timedelta(hours=3), ends_at=now() - timedelta(hours=2))
    db.add(l2)
    await db.flush()
    l2 = l2.id
    await db.commit()
    r = await client.put(f"/api/lessons/{l2}/attendance", headers=owner_h, json={**marks, "reason": "позже"})
    assert r.status_code == 200, r.text
    acc = await db.scalar(select(Accrual).where(Accrual.kind == "lesson", Accrual.ref_id == l2))
    assert acc.amount == 5000  # the course rate, no per-student extra on top
    p = (await client.get(f"/api/payroll/person?user_id={teacher_id}&period={period_of(today())}", headers=owner_h)).json()
    assert (p["rate_total"], p["kpi_total"]) == (7500, 200)


async def test_second_lesson_of_the_day_is_not_marked_and_old_duplicates_are_undone(client, db, owner_h):
    from datetime import time

    from app.models import ScheduleRule, Student
    from app.services import dupes
    from app.services.clock import at_local, local, today
    from tests.test_core_learning import _setup, _student

    bid, teacher, room, g = await _setup(db, client, owner_h)
    tid, rid, gid = teacher.id, room.id, g["id"]
    sid = (await _student(db, client, owner_h, bid, "Дубль Урок", "+77052227111"))["id"]
    day = today() - timedelta(days=3)
    await client.post(f"/api/groups/{gid}/members", headers=owner_h, json={"student_id": sid, "joined_on": (day - timedelta(days=2)).isoformat()})
    await client.post("/api/payments", headers=owner_h, json={"student_id": sid, "lessons": 8, "method": "cash", "level_id": g["level_id"]})
    r1 = ScheduleRule(group_id=gid, weekdays=[day.weekday()], start_time=time(16, 30), end_time=time(17, 30), room_id=rid, teacher_id=tid,
                      valid_from=day - timedelta(days=30), valid_to=day)
    r2 = ScheduleRule(group_id=gid, weekdays=[day.weekday()], start_time=time(15, 0), end_time=time(16, 0), room_id=rid, teacher_id=tid,
                      valid_from=day - timedelta(days=30))
    db.add_all([r1, r2])
    await db.flush()
    old = Lesson(branch_id=bid, group_id=gid, level_id=g["level_id"], teacher_id=tid, room_id=rid, rule_id=r1.id,
                 starts_at=at_local(day, time(16, 30)), ends_at=at_local(day, time(17, 30)), created_at=now() - timedelta(days=10))
    new = Lesson(branch_id=bid, group_id=gid, level_id=g["level_id"], teacher_id=tid, room_id=rid, rule_id=r2.id,
                 starts_at=at_local(day, time(15, 0)), ends_at=at_local(day, time(16, 0)))
    db.add_all([old, new])
    await db.flush()
    old_id, new_id, r2_id = old.id, new.id, r2.id
    await db.commit()
    marks = {"marks": [{"student_id": sid, "status": "present"}], "reason": "позже"}
    assert (await client.put(f"/api/lessons/{old_id}/attendance", headers=owner_h, json=marks)).status_code == 200
    r = await client.put(f"/api/lessons/{new_id}/attendance", headers=owner_h, json=marks)
    assert r.status_code == 409 and "уже отмечен" in r.json()["detail"]  # the second time is refused

    # «Прошедшие уроки» does not put a second lesson on a day that already has one
    rule2 = await db.get(ScheduleRule, r2_id)
    await db.delete(await db.get(Lesson, new_id))
    await db.commit()
    from app.models import Group
    from app.modules.academics import schedule as sched
    made, _ = await sched.backfill(db, rule2, await db.get(Group, gid), day, day)
    assert made == 0

    # what was doubled before the guard existed: both marked, the student charged twice, the teacher paid twice
    dup = Lesson(branch_id=bid, group_id=gid, level_id=g["level_id"], teacher_id=tid, room_id=rid, rule_id=r2_id,
                 starts_at=at_local(day, time(15, 0)), ends_at=at_local(day, time(16, 0)), status="done", attendance_marked_at=now())
    db.add(dup)
    await db.flush()
    dup_id = dup.id
    from app.models import Attendance
    db.add(Attendance(lesson_id=dup_id, student_id=sid, status="present", charged=True, marked_by=tid))
    db.add(Accrual(user_id=tid, kind="lesson", amount=2500, ref_type="lesson", ref_id=dup_id, period=f"{day:%Y-%m}", branch_id=bid,
                   description="Урок EL-5: 1 уч."))
    s = await db.get(Student, sid)
    s.lessons_left -= 1
    s.lessons_done += 1
    await db.commit()
    left = (await client.get(f"/api/students/{sid}", headers=owner_h)).json()["lessons_left"]
    pre = await dupes.find(db, day - timedelta(days=1), "old")
    assert [(x["lesson_id"], x["keep_id"], x["charged"], x["pay"]) for x in pre] == [(dup_id, old_id, 1, 2500)]
    assert [(x["lesson_id"], x["keep_id"]) for x in await dupes.find(db, day - timedelta(days=1), "new")] == [(old_id, dup_id)]
    res = await dupes.fix(db, day - timedelta(days=1), "old", None)
    assert (res["lessons"], res["returned_to_students"], res["teacher_pay_removed"]) == (1, 1, 2500)
    assert (await client.get(f"/api/students/{sid}", headers=owner_h)).json()["lessons_left"] == left + 1
    assert await db.scalar(select(Accrual.amount).where(Accrual.ref_type == "lesson", Accrual.ref_id == dup_id)) == 0
    assert await db.scalar(select(Accrual.amount).where(Accrual.ref_type == "lesson", Accrual.ref_id == old_id)) == 2500
    assert await dupes.find(db, day - timedelta(days=1), "old") == []
    att = (await client.get(f"/api/students/{sid}/attendance", headers=owner_h)).json()
    assert [a["lesson_id"] for a in att] == [old_id]
