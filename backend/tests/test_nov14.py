"""Owner's requests of 14.11.2026: late freeze, payment fix, old subscriptions, methodist tasks, leaving through the
methodist, pay breakdown, substitution, book out of a payment, finance by dates."""

from datetime import timedelta

from sqlalchemy import select

from app.models import Accrual, Lesson, Payment, Role, Student, Task, TaskAssignee, UserRole
from app.services.clock import now, today
from tests.conftest import level_id, login, make_staff
from tests.test_core_learning import YANGI, _lesson_now, _setup, _student


async def _methodist(db, phone="+77030000701"):
    role = Role(name="Методист", code="methodist")
    db.add(role)
    await db.flush()
    u = await make_staff(db, "office_manager", [YANGI], phone, "Мадина Методист")
    db.add(UserRole(user_id=u.id, role_id=role.id))
    await db.flush()
    return u


async def _past_lesson(db, g, teacher, room, days_ago, minutes=0):
    start = now() - timedelta(days=days_ago, minutes=minutes)
    lesson = Lesson(branch_id=g["branch_id"], group_id=g["id"], level_id=g["level_id"], teacher_id=teacher.id, room_id=room.id,
                    starts_at=start, ends_at=start + timedelta(minutes=80))
    db.add(lesson)
    await db.flush()
    return lesson


async def test_late_freeze_returns_charged_absences(db, client, owner_h):
    bid, teacher, room, g = await _setup(db, client, owner_h)
    s = await _student(db, client, owner_h, bid)
    await client.post(f"/api/groups/{g['id']}/members", headers=owner_h, json={"student_id": s["id"]})
    st = await db.get(Student, s["id"])
    from app.models import GroupMember
    m = await db.scalar(select(GroupMember).where(GroupMember.student_id == st.id))
    m.joined_on = today() - timedelta(days=10)
    await client.post("/api/payments", headers=owner_h, json={"student_id": s["id"], "lessons": 12, "method": "cash"})
    lesson = await _past_lesson(db, g, teacher, room, 2)
    r = await client.put(f"/api/lessons/{lesson.id}/attendance", headers=owner_h,
                         json={"marks": [{"student_id": s["id"], "status": "absent"}], "reason": "поздняя отметка"})
    assert r.status_code == 200, r.text
    await db.refresh(st)
    assert st.lessons_left == 11
    body = {"starts_on": str(today() - timedelta(days=3)), "ends_on": str(today() + timedelta(days=4)), "reason": "болел"}
    r = await client.post(f"/api/students/{s['id']}/freeze", headers=owner_h, json=body)
    assert r.status_code == 200, r.text
    await db.refresh(st)
    assert st.lessons_left == 12 and st.status == "frozen"
    old = {"starts_on": str(today() - timedelta(days=90)), "ends_on": str(today() - timedelta(days=80))}
    assert (await client.post(f"/api/students/{s['id']}/freeze", headers=owner_h, json=old)).status_code == 400


async def test_payment_fix_lessons_level_amount(db, client, owner_h):
    bid, teacher, room, g = await _setup(db, client, owner_h)
    s = await _student(db, client, owner_h, bid)
    p = (await client.post("/api/payments", headers=owner_h, json={"student_id": s["id"], "lessons": 12, "method": "cash"})).json()
    office = await make_staff(db, "office_manager", [YANGI], "+77030000702")
    oh = await login(client, office.phone)
    assert (await client.patch(f"/api/payments/{p['id']}", headers=oh, json={"lessons": 8})).status_code == 403
    r = await client.patch(f"/api/payments/{p['id']}", headers=owner_h, json={"lessons": 8, "amount": 24000})
    assert r.status_code == 200, r.text
    assert r.json()["lessons"] == 8 and r.json()["amount"] == 24000
    st = await db.get(Student, s["id"])
    await db.refresh(st)
    assert (st.lessons_paid, st.lessons_left) == (8, 8)
    r = await client.patch(f"/api/payments/{p['id']}", headers=owner_h, json={"lessons": 10, "level_id": await level_id(db, "PRE")})
    assert r.status_code == 200, r.text
    await db.refresh(st)
    assert st.lessons_left == 10 and r.json()["level_id"] == await level_id(db, "PRE")


async def test_old_subscription_with_past_date_and_used_lessons(db, client, owner_h):
    bid, teacher, room, g = await _setup(db, client, owner_h)
    s = await _student(db, client, owner_h, bid)
    pkg = (await client.post("/api/packages", headers=owner_h, json={"name": "6 месяцев", "months": 6, "price": 180000, "lessons": 72})).json()
    paid = today() - timedelta(days=70)
    r = await client.post("/api/payments", headers=owner_h, json={
        "student_id": s["id"], "package_id": pkg["id"], "method": "kaspi", "paid_on": paid.isoformat(), "used_lessons": 24})
    assert r.status_code == 201, r.text
    assert r.json()["amount"] == 180000 and r.json()["lessons"] == 48
    assert r.json()["valid_to"] > today().isoformat()
    st = await db.get(Student, s["id"])
    await db.refresh(st)
    assert st.lessons_left == 48


async def test_two_absences_in_a_row_make_a_task_for_methodist(db, client, owner_h):
    bid, teacher, room, g = await _setup(db, client, owner_h)
    meth = await _methodist(db)
    s = await _student(db, client, owner_h, bid)
    await client.post(f"/api/groups/{g['id']}/members", headers=owner_h, json={"student_id": s["id"]})
    from app.models import GroupMember
    m = await db.scalar(select(GroupMember).where(GroupMember.student_id == s["id"]))
    m.joined_on = today() - timedelta(days=10)
    l1 = await _past_lesson(db, g, teacher, room, 3)
    l2 = await _past_lesson(db, g, teacher, room, 1)
    for lesson in (l1, l2):
        r = await client.put(f"/api/lessons/{lesson.id}/attendance", headers=owner_h,
                             json={"marks": [{"student_id": s["id"], "status": "absent"}], "reason": "отметка"})
        assert r.status_code == 200, r.text
        tasks = list(await db.scalars(select(Task).where(Task.auto_kind == "absence2", Task.link_id == s["id"])))
        assert len(tasks) == (0 if lesson is l1 else 1)
    assert await db.scalar(select(TaskAssignee.user_id).where(TaskAssignee.task_id == tasks[0].id)) == meth.id
    # marking again does not duplicate the open task
    await client.put(f"/api/lessons/{l2.id}/attendance", headers=owner_h,
                     json={"marks": [{"student_id": s["id"], "status": "excused"}], "reason": "исправление"})
    assert len(list(await db.scalars(select(Task).where(Task.auto_kind == "absence2")))) == 1


async def test_leaving_goes_through_the_methodist(db, client, owner_h):
    bid, teacher, room, g = await _setup(db, client, owner_h)
    meth = await _methodist(db)
    office = await make_staff(db, "office_manager", [YANGI], "+77030000703")
    oh, mh = await login(client, office.phone), await login(client, meth.phone)
    s = await _student(db, client, owner_h, bid)
    r = await client.patch(f"/api/students/{s['id']}", headers=oh, json={"status": "left", "leave_reason": "говорит, дорого"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "active" and r.json()["leave_request"] and not r.json()["can_decide_leave"]
    task = await db.scalar(select(Task).where(Task.auto_kind == "leave", Task.link_id == s["id"]))
    assert task is not None and "дорого" in task.description
    assert (await client.post(f"/api/students/{s['id']}/leave-decision", headers=oh, json={"left": True, "reason": "дорого"})).status_code == 403
    r = await client.post(f"/api/students/{s['id']}/leave-decision", headers=mh,
                          json={"left": True, "reason": "Переезд в Алматы", "return_note": "вернётся летом"})
    assert r.status_code == 200, r.text
    card = r.json()
    assert card["status"] == "left" and card["leave_reason"] == "Переезд в Алматы" and card["leave_request"] is None
    await db.refresh(task)
    assert task.status == "done"
    texts = [x["text"] for x in (await client.get(f"/api/students/{s['id']}/history", headers=owner_h)).json()]
    assert any("Переезд в Алматы" in x and "вернётся летом" in x for x in texts)
    # the methodist sets «ушёл» directly, but only with a reason
    s2 = await _student(db, client, owner_h, bid, "Второй Ученик", "+77051112244")
    assert (await client.patch(f"/api/students/{s2['id']}", headers=mh, json={"status": "left"})).status_code == 400
    r = await client.patch(f"/api/students/{s2['id']}", headers=mh, json={"status": "left", "leave_reason": "не понравилось"})
    assert r.status_code == 200 and r.json()["status"] == "left"
    # «stays»
    s3 = await _student(db, client, owner_h, bid, "Третий Ученик", "+77051112255")
    await client.patch(f"/api/students/{s3['id']}", headers=oh, json={"status": "left"})
    r = await client.post(f"/api/students/{s3['id']}/leave-decision", headers=mh, json={"left": False, "reason": "Договорились о рассрочке"})
    assert r.json()["status"] == "active" and r.json()["leave_request"] is None


async def test_substitute_gets_the_pay_and_may_overlap(db, client, owner_h):
    bid, teacher, room, g = await _setup(db, client, owner_h)
    sub = await make_staff(db, "teacher", [YANGI], "+77020000705", "Замена Учитель")
    s = await _student(db, client, owner_h, bid)
    await client.post(f"/api/groups/{g['id']}/members", headers=owner_h, json={"student_id": s["id"]})
    lesson = await _lesson_now(db, g, teacher, room)
    # the substitute already has a lesson of their own at the same time
    from app.models import Room
    room2 = (await db.scalars(select(Room).where(Room.branch_id == bid).order_by(Room.id))).all()[1]
    db.add(Lesson(branch_id=bid, teacher_id=sub.id, room_id=room2.id, student_id=s["id"], starts_at=lesson.starts_at, ends_at=lesson.ends_at))
    await db.flush()
    r = await client.put(f"/api/lessons/{lesson.id}/attendance", headers=owner_h, json={"marks": [{"student_id": s["id"], "status": "present"}]})
    assert r.status_code == 200, r.text
    acc = await db.scalar(select(Accrual).where(Accrual.kind == "lesson", Accrual.ref_id == lesson.id))
    assert acc.user_id == teacher.id
    r = await client.post(f"/api/lessons/{lesson.id}/substitute", headers=owner_h, json={"teacher_id": sub.id})
    assert r.status_code == 200, r.text
    assert r.json()["actual_teacher_id"] == sub.id
    await db.refresh(acc)
    assert acc.user_id == sub.id and acc.amount == 2500


async def test_book_out_of_a_course_payment(db, client, owner_h):
    bid, teacher, room, g = await _setup(db, client, owner_h)
    s = await _student(db, client, owner_h, bid)
    b = (await client.post("/api/books", headers=owner_h, json={
        "title": "Elementary SB", "level_id": await level_id(db, "ELE"), "sale_price": 4000, "purchase_price": 2500})).json()
    await client.post("/api/books/receive", headers=owner_h, json={"branch_id": bid, "book_id": b["id"], "qty": 5, "unit_price": 2500})
    body = {"student_id": s["id"], "book_id": b["id"], "from_payment": True}
    r = await client.post("/api/books/sell", headers=owner_h, json=body)
    assert r.status_code == 400 and "ещё не получена" in r.json()["detail"]
    p = (await client.post("/api/payments", headers=owner_h, json={"student_id": s["id"], "amount": 33500, "method": "kaspi"})).json()
    assert p["lessons"] == 11  # 33 000 → 11 lessons, 500 on the balance
    assert (await client.get(f"/api/students/{s['id']}", headers=owner_h)).json()["book_from_payment"] == 33500
    r = await client.post("/api/books/sell", headers=owner_h, json=body)
    assert r.status_code == 201, r.text
    src = await db.get(Payment, p["id"])
    await db.refresh(src)
    book = await db.get(Payment, r.json()["payment_id"])
    assert src.amount == 29500 and book.amount == 4000 and book.category == "book" and book.method == "kaspi"
    st = await db.get(Student, s["id"])
    await db.refresh(st)
    # 4 000 = 500 from the money balance + 2 lessons (6 000) → 2 500 back on the money balance
    assert st.lessons_left == 9 and st.money_balance == 2500 and src.lessons == 9
    assert st.lessons_left * 3000 + st.money_balance == 29500


async def test_pay_breakdown_and_finance_by_dates(db, client, owner_h):
    bid, teacher, room, g = await _setup(db, client, owner_h)
    ids = []
    for i in range(7):
        s = await _student(db, client, owner_h, bid, f"Ученик {i}", f"+7705111230{i}")
        await client.post(f"/api/groups/{g['id']}/members", headers=owner_h, json={"student_id": s["id"]})
        ids.append(s["id"])
    lesson = await _lesson_now(db, g, teacher, room)
    await client.put(f"/api/lessons/{lesson.id}/attendance", headers=owner_h,
                     json={"marks": [{"student_id": i, "status": "present"} for i in ids]})
    start = (now() - timedelta(minutes=3)).replace(microsecond=0)
    sup = (await client.post("/api/lessons", headers=owner_h, json={
        "teacher_id": teacher.id, "room_id": room.id, "starts_at": (start + timedelta(hours=3)).isoformat(),
        "ends_at": (start + timedelta(hours=4)).isoformat(), "support": True, "topic": "Speaking"})).json()
    sl = await db.get(Lesson, sup["id"])
    sl.starts_at, sl.ends_at = start - timedelta(hours=3), start - timedelta(hours=2)
    await db.flush()
    r = await client.put(f"/api/lessons/{sup['id']}/attendance", headers=owner_h, json={"marks": [], "reason": "проведён"})
    assert r.status_code == 200, r.text
    bd = (await client.get(f"/api/payroll/breakdown?user_id={teacher.id}", headers=owner_h)).json()
    rows = {x["key"]: x for x in bd["lessons"]}
    assert rows["group"] == {"key": "group", "title": "Групповые уроки", "count": 1, "amount": 2500}
    assert rows["support"]["amount"] == 1000 and bd["kpi"]["amount"] == 200 and bd["total"] == 3700
    assert bd["lessons_count"] == 2 and bd["lessons_total"] == 3500
    th = await login(client, teacher.phone)
    assert (await client.get("/api/payroll/my", headers=th)).json()["breakdown"]["kpi"]["amount"] == 200
    # finance for a range of days: receipts, refunds, net revenue by category
    p = (await client.post("/api/payments", headers=owner_h, json={"student_id": ids[0], "lessons": 12, "method": "cash"})).json()
    await client.post(f"/api/payments/{p['id']}/refund", headers=owner_h, json={"lessons": 2, "amount": 6000, "reason": "по заявлению"})
    d = today().isoformat()
    pnl = (await client.get(f"/api/finance/pnl?date_from={d}&date_to={d}", headers=owner_h)).json()
    assert pnl["total"]["receipts"] == 36000 and pnl["total"]["refunds"] == 6000 and pnl["total"]["net_revenue"] == 30000
    row = next(x for x in pnl["branches"] if x["branch_id"] == bid)
    assert row["net_by_category"] == {"course": 30000} and row["payroll"] == 3700
    y = (today() - timedelta(days=1)).isoformat()
    assert (await client.get(f"/api/finance/pnl?date_from={y}&date_to={y}", headers=owner_h)).json()["total"]["receipts"] == 0
