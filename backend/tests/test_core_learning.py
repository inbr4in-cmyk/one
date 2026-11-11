from datetime import time, timedelta

from sqlalchemy import select

from app.models import Accrual, Lesson, Room, Student
from app.services.balance import calc_transfer
from app.services.clock import at_local, now, today
from app.services.payroll import teacher_lesson_pay
from tests.conftest import branch_id, level_id, login, make_staff

YANGI = "Янги шахар"


def test_transfer_formula_examples_from_tz():
    c = calc_transfer(4, 0, 3000, 4000)
    assert (c.value, c.lessons_after, c.money_after) == (12000, 3, 0)
    c = calc_transfer(4, 1000, 3000, 4000)  # 13 000 → 3 lessons + 1 000 money
    assert (c.lessons_after, c.money_after) == (3, 1000)
    c = calc_transfer(5, 0, 3000, 3000)
    assert c.same_price and c.lessons_after == 5


def test_teacher_formula():
    assert teacher_lesson_pay(8, 2500, 100, 5) == 2800
    assert teacher_lesson_pay(5, 2500, 100, 5) == 2500
    assert teacher_lesson_pay(2, 2500, 100, 5) == 2500


async def _setup(db, client, owner_h):
    bid = await branch_id(db, YANGI)
    teacher = await make_staff(db, "teacher", [YANGI], "+77020000001", "Дана Учитель")
    room = await db.scalar(select(Room).where(Room.branch_id == bid).order_by(Room.id))
    r = await client.post("/api/groups", headers=owner_h, json={
        "name": "EL-5", "branch_id": bid, "level_id": await level_id(db, "ELE"), "teacher_id": teacher.id, "room_id": room.id,
        "capacity": 12})
    assert r.status_code == 201, r.text
    return bid, teacher, room, r.json()


async def test_schedule_generation_and_conflicts(db, client, owner_h):
    bid, teacher, room, g = await _setup(db, client, owner_h)
    start = today() + timedelta(days=1)
    r = await client.post(f"/api/groups/{g['id']}/schedule", headers=owner_h, json={
        "weekdays": [0, 2, 4], "start_time": "16:00", "end_time": "17:30", "room_id": room.id, "valid_from": start.isoformat()})
    assert r.status_code == 201, r.text
    assert r.json()["created"] >= 20 and r.json()["conflicts"] == []
    # Second group in the same room and time → conflicts reported, no lessons created for those slots
    t2 = await make_staff(db, "teacher", [YANGI], "+77020000002")
    g2 = (await client.post("/api/groups", headers=owner_h, json={
        "name": "PI-3", "branch_id": bid, "level_id": await level_id(db, "PRE"), "teacher_id": t2.id, "capacity": 10})).json()
    r = await client.post(f"/api/groups/{g2['id']}/schedule", headers=owner_h, json={
        "weekdays": [0], "start_time": "17:00", "end_time": "18:00", "room_id": room.id, "valid_from": start.isoformat()})
    assert r.status_code == 409 and "пересекаются" in r.json()["detail"]
    # Same teacher in another room at the same time → conflict too
    other_room = await db.scalar(select(Room).where(Room.branch_id == bid, Room.id != room.id))
    nxt = next(start + timedelta(days=i) for i in range(7) if (start + timedelta(days=i)).weekday() == 0)
    r = await client.post("/api/lessons", headers=owner_h, json={
        "group_id": g2["id"], "teacher_id": teacher.id, "room_id": other_room.id,
        "starts_at": at_local(nxt, time(16, 30)).isoformat(), "ends_at": at_local(nxt, time(17, 0)).isoformat()})
    assert r.status_code == 409 and "Учитель занят" in r.json()["detail"]


async def test_schedule_skips_group_own_imported_lessons(db, client, owner_h):
    """Lessons of the same group (e.g. imported from the old CRM) are not a conflict for its new schedule."""
    bid, teacher, room, g = await _setup(db, client, owner_h)
    start = today() + timedelta(days=1)
    nxt = next(start + timedelta(days=i) for i in range(7) if (start + timedelta(days=i)).weekday() == 1)
    db.add(Lesson(branch_id=bid, group_id=g["id"], level_id=g["level_id"], teacher_id=teacher.id, room_id=room.id,
                  starts_at=at_local(nxt, time(10)), ends_at=at_local(nxt, time(11, 30))))
    await db.commit()
    r = await client.post(f"/api/groups/{g['id']}/schedule", headers=owner_h, json={
        "weekdays": [1], "start_time": "10:00", "end_time": "11:30", "room_id": room.id, "valid_from": start.isoformat()})
    assert r.status_code == 201, r.text
    assert r.json()["conflicts"] == [] and r.json()["created"] >= 5
    n = len((await db.scalars(select(Lesson).where(Lesson.group_id == g["id"], Lesson.starts_at == at_local(nxt, time(10))))).all())
    assert n == 1  # the imported lesson is kept, no duplicate


async def _student(db, client, h, bid, name="Алия Нурланова", phone="+77051112233"):
    r = await client.post("/api/students", headers=h, json={
        "full_name": name, "phone": phone, "branch_id": bid, "level_id": await level_id(db, "ELE"),
        "guardians": [{"full_name": "Сауле Нурланова", "phone": "+7705" + phone[-7:-1] + "9", "relation": "мама"}]})
    assert r.status_code == 201, r.text
    return r.json()


async def _lesson_now(db, g, teacher, room):
    lesson = Lesson(branch_id=g["branch_id"], group_id=g["id"], level_id=g["level_id"], teacher_id=teacher.id, room_id=room.id,
                    starts_at=now() - timedelta(minutes=5), ends_at=now() + timedelta(minutes=85))
    db.add(lesson)
    await db.flush()
    return lesson


async def test_payment_attendance_balance_and_teacher_pay(db, client, owner_h):
    bid, teacher, room, g = await _setup(db, client, owner_h)
    ids = []
    for i in range(8):
        s = await _student(db, client, owner_h, bid, f"Ученик {i}", f"+7705111220{i}")
        assert (await client.post(f"/api/groups/{g['id']}/members", headers=owner_h, json={"student_id": s["id"]})).status_code == 201
        ids.append(s["id"])
    office = await make_staff(db, "office_manager", [YANGI], "+77030000001")
    oh = await login(client, office.phone)
    r = await client.post("/api/payments", headers=oh, json={"student_id": ids[0], "lessons": 12, "method": "kaspi"})
    assert r.status_code == 201, r.text
    assert r.json()["amount"] == 12 * 3000  # ТЗ 5.2: 12 × 3000 = 36 000
    lesson = await _lesson_now(db, g, teacher, room)
    th = await login(client, teacher.phone)
    marks = [{"student_id": sid, "status": "present"} for sid in ids]
    r = await client.put(f"/api/lessons/{lesson.id}/attendance", headers=th, json={"marks": marks})
    assert r.status_code == 200, r.text
    s0 = await db.get(Student, ids[0])
    await db.refresh(s0)
    assert (s0.lessons_paid, s0.lessons_done, s0.lessons_left) == (12, 1, 11)
    acc = await db.scalar(select(Accrual).where(Accrual.kind == "lesson", Accrual.ref_id == lesson.id))
    assert acc.amount == 2800 and acc.user_id == teacher.id
    # Re-marking two as excused: they get the lesson back and the pay follows N = 6
    marks[1]["status"] = marks[2]["status"] = "excused"
    r = await client.put(f"/api/lessons/{lesson.id}/attendance", headers=th, json={"marks": marks})
    assert r.status_code == 200
    await db.refresh(acc)
    assert acc.amount == 2600
    # No duplicate accrual rows for the same lesson
    assert len((await db.scalars(select(Accrual).where(Accrual.kind == "lesson", Accrual.ref_id == lesson.id))).all()) == 1


async def test_teacher_cannot_mark_next_day_admin_can_with_reason(db, client, owner_h):
    bid, teacher, room, g = await _setup(db, client, owner_h)
    s = await _student(db, client, owner_h, bid)
    await client.post(f"/api/groups/{g['id']}/members", headers=owner_h, json={"student_id": s["id"]})
    from app.models import GroupMember

    for m in await db.scalars(select(GroupMember).where(GroupMember.student_id == s["id"])):
        m.joined_on = today() - timedelta(days=30)
    lesson = Lesson(branch_id=bid, group_id=g["id"], level_id=g["level_id"], teacher_id=teacher.id, room_id=room.id,
                    starts_at=now() - timedelta(days=2), ends_at=now() - timedelta(days=2) + timedelta(minutes=90))
    db.add(lesson)
    await db.flush()
    th = await login(client, teacher.phone)
    body = {"marks": [{"student_id": s["id"], "status": "present"}]}
    assert (await client.put(f"/api/lessons/{lesson.id}/attendance", headers=th, json=body)).status_code == 403
    admin = await make_staff(db, "branch_admin", [YANGI], "+77040000001")
    ah = await login(client, admin.phone)
    assert (await client.put(f"/api/lessons/{lesson.id}/attendance", headers=ah, json=body)).status_code == 400
    r = await client.put(f"/api/lessons/{lesson.id}/attendance", headers=ah, json={**body, "reason": "Учитель забыл отметить"})
    assert r.status_code == 200


async def test_sales_cannot_take_payment_and_branch_isolation(db, client, owner_h):
    bid = await branch_id(db, YANGI)
    s = await _student(db, client, owner_h, bid)
    sales = await make_staff(db, "sales", [YANGI], "+77060000001")
    sh = await login(client, sales.phone)
    r = await client.post("/api/payments", headers=sh, json={"student_id": s["id"], "lessons": 4, "method": "cash"})
    assert r.status_code == 403
    north_admin = await make_staff(db, "branch_admin", ["Север"], "+77060000002")
    nh = await login(client, north_admin.phone)
    assert (await client.get(f"/api/students/{s['id']}", headers=nh)).status_code == 404
    lst = (await client.get("/api/students", headers=nh)).json()
    assert all(x["id"] != s["id"] for x in lst["items"])
    # Phones are masked for roles without view_contacts
    teacher = await make_staff(db, "teacher", [YANGI], "+77060000003")
    th = await login(client, teacher.phone)
    assert (await client.get(f"/api/students/{s['id']}", headers=th)).status_code == 404  # not their student


async def test_transfer_to_pricier_level(db, client, owner_h):
    bid, teacher, room, g = await _setup(db, client, owner_h)
    s = await _student(db, client, owner_h, bid)
    await client.post(f"/api/groups/{g['id']}/members", headers=owner_h, json={"student_id": s["id"]})
    await client.post("/api/payments", headers=owner_h, json={"student_id": s["id"], "lessons": 4, "method": "cash"})
    g2 = (await client.post("/api/groups", headers=owner_h, json={
        "name": "INT-1", "branch_id": bid, "level_id": await level_id(db, "INT"), "teacher_id": teacher.id})).json()
    p = (await client.post(f"/api/students/{s['id']}/transfer/preview", headers=owner_h, json={"to_group_id": g2["id"]})).json()
    assert (p["value"], p["lessons_after"], p["money_after"]) == (12000, 3, 0)
    r = await client.post(f"/api/students/{s['id']}/transfer", headers=owner_h, json={"to_group_id": g2["id"], "reason": "Сдал тест"})
    assert r.status_code == 200, r.text
    card = r.json()
    assert card["balance"]["lessons_left"] == 3 and card["group_names"] == ["INT-1"]
    assert card["balance"]["lessons_paid"] == card["balance"]["lessons_done"] + card["balance"]["lessons_left"]


async def test_role_builder_privilege_escalation(db, client, owner_h):
    admin = await make_staff(db, "branch_admin", [YANGI], "+77070000001")
    # Grant roles.manage to the admin via a custom role so we can test the guard
    r = await client.post("/api/roles", headers=owner_h, json={"name": "Менеджер ролей", "code": "role_mgr", "permissions": [
        {"module": "roles", "action": "manage", "scope": "branch"}, {"module": "roles", "action": "view", "scope": "branch"}]})
    assert r.status_code == 201
    from app.models import UserRole

    db.add(UserRole(user_id=admin.id, role_id=r.json()["id"]))
    await db.flush()
    ah = await login(client, admin.phone)
    r = await client.post("/api/roles", headers=ah, json={"name": "Хитрая", "permissions": [
        {"module": "finance", "action": "view", "scope": "network"}]})
    assert r.status_code == 403
    r = await client.post("/api/roles", headers=ah, json={"name": "Нормальная", "permissions": [
        {"module": "students", "action": "view", "scope": "branch"}]})
    assert r.status_code == 201


async def test_edit_student_card_managers_only_and_login_follows_phone(db, client, owner_h):
    from app.models import User

    bid, teacher, room, g = await _setup(db, client, owner_h)
    s = await _student(db, client, owner_h, bid)
    other = await _student(db, client, owner_h, bid, name="Другой Ученик", phone="+77051119988")
    office = await make_staff(db, "office_manager", [YANGI], "+77020000005", "Офис Менеджер")
    th = await login(client, teacher.phone)
    r = await client.patch(f"/api/students/{s['id']}", headers=th, json={"full_name": "Взлом"})
    assert r.status_code == 403
    oh = await login(client, office.phone)
    r = await client.patch(f"/api/students/{s['id']}", headers=oh, json={"phone": other["phone"]})
    assert r.status_code == 409
    r = await client.patch(f"/api/students/{s['id']}", headers=oh, json={"full_name": "Алия Серикова", "phone": "+77051110000",
                                                                           "notes": "перешла на утро"})
    assert r.status_code == 200, r.text
    assert r.json()["full_name"] == "Алия Серикова"
    st = await db.get(Student, s["id"])
    await db.refresh(st)
    u = await db.get(User, st.user_id)
    await db.refresh(u)
    assert u.phone == "+77051110000" and u.full_name == "Алия Серикова"


async def test_backdated_payment_admin_only_no_notification(db, client, owner_h):
    from app.models import OutboundMessage, Payment
    from app.services.clock import local

    bid, teacher, room, g = await _setup(db, client, owner_h)
    s = await _student(db, client, owner_h, bid)
    office = await make_staff(db, "office_manager", [YANGI], "+77020000006", "Офис Два")
    past = (today() - timedelta(days=20)).isoformat()
    oh = await login(client, office.phone)
    r = await client.post("/api/payments", headers=oh, json={"student_id": s["id"], "lessons": 8, "method": "cash", "paid_on": past})
    assert r.status_code == 403
    future = (today() + timedelta(days=1)).isoformat()
    r = await client.post("/api/payments", headers=owner_h, json={"student_id": s["id"], "lessons": 8, "method": "cash", "paid_on": future})
    assert r.status_code in (400, 422)
    r = await client.post("/api/payments", headers=owner_h, json={"student_id": s["id"], "lessons": 8, "method": "cash", "paid_on": past})
    assert r.status_code == 201, r.text
    p = await db.get(Payment, r.json()["id"])
    assert local(p.paid_at).date().isoformat() == past
    sent = await db.scalar(select(OutboundMessage.id).where(OutboundMessage.template_code == "payment"))
    assert sent is None


async def test_partial_payment_any_amount(db, client, owner_h):
    from app.models import Level

    bid, teacher, room, g = await _setup(db, client, owner_h)
    s = await _student(db, client, owner_h, bid)
    price = (await db.get(Level, g["level_id"])).lesson_price
    r = await client.post("/api/payments", headers=owner_h, json={"student_id": s["id"], "method": "cash", "amount": price + price // 2})
    assert r.status_code == 201, r.text
    assert r.json()["lessons"] == 1 and r.json()["amount"] == price + price // 2
    st = await db.get(Student, s["id"])
    await db.refresh(st)
    assert st.lessons_left == 1 and st.money_balance == price // 2
    r = await client.post("/api/payments", headers=owner_h, json={"student_id": s["id"], "method": "kaspi", "amount": price - price // 2})
    assert r.status_code == 201, r.text
    await db.refresh(st)
    assert st.lessons_left == 2 and st.money_balance == 0
    r = await client.post("/api/payments/quote", headers=owner_h, json={"student_id": s["id"], "method": "cash", "amount": 100, "discount": 50})
    assert r.status_code == 400


async def test_backfill_past_lessons_from_schedule(db, client, owner_h):
    """Schedules entered late: an admin creates the past lessons for a period; members show on their rosters."""
    from app.models import GroupMember
    bid, teacher, room, g = await _setup(db, client, owner_h)
    r = await client.post(f"/api/groups/{g['id']}/schedule", headers=owner_h, json={
        "weekdays": [0, 1, 2, 3, 4, 5, 6], "start_time": "10:00", "end_time": "11:00", "room_id": room.id,
        "valid_from": today().isoformat()})
    assert r.status_code == 201, r.text
    s = await _student(db, client, owner_h, bid)
    assert (await client.post(f"/api/groups/{g['id']}/members", headers=owner_h, json={"student_id": s["id"]})).status_code == 201
    frm, to = today() - timedelta(days=10), today() - timedelta(days=1)
    # existing past lesson of the group is kept, not duplicated
    db.add(Lesson(branch_id=bid, group_id=g["id"], level_id=g["level_id"], teacher_id=teacher.id, room_id=room.id,
                  starts_at=at_local(frm, time(10)), ends_at=at_local(frm, time(11))))
    await db.commit()
    th = await login(client, teacher.phone)
    body = {"date_from": frm.isoformat(), "date_to": to.isoformat()}
    assert (await client.post("/api/schedule/backfill", headers=th, json=body)).status_code == 403
    assert (await client.post("/api/schedule/backfill", headers=owner_h,
                              json={"date_from": frm.isoformat(), "date_to": today().isoformat()})).status_code == 400
    r = await client.post("/api/schedule/backfill", headers=owner_h, json=body)
    assert r.status_code == 200, r.text
    assert r.json()["created"] == 9 and r.json()["members"] == 1
    past = (await db.scalars(select(Lesson).where(Lesson.group_id == g["id"], Lesson.starts_at < at_local(today(), time(0))))).all()
    assert len(past) == 10
    m = await db.scalar(select(GroupMember).where(GroupMember.group_id == g["id"]))
    await db.refresh(m)
    assert m.joined_on == frm
    lesson = next(x for x in past if x.rule_id)
    roster = await client.get(f"/api/lessons/{lesson.id}/attendance", headers=owner_h)
    assert [x["student_id"] for x in roster.json()["rows"]] == [s["id"]]
    again = await client.post("/api/schedule/backfill", headers=owner_h, json=body)
    assert again.json()["created"] == 0
