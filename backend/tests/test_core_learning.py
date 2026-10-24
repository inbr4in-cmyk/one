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
    assert r.json()["created"] == 0 and r.json()["conflicts"]
    # Same teacher in another room at the same time → conflict too
    other_room = await db.scalar(select(Room).where(Room.branch_id == bid, Room.id != room.id))
    nxt = next(start + timedelta(days=i) for i in range(7) if (start + timedelta(days=i)).weekday() == 0)
    r = await client.post("/api/lessons", headers=owner_h, json={
        "group_id": g2["id"], "teacher_id": teacher.id, "room_id": other_room.id,
        "starts_at": at_local(nxt, time(16, 30)).isoformat(), "ends_at": at_local(nxt, time(17, 0)).isoformat()})
    assert r.status_code == 409 and "Учитель занят" in r.json()["detail"]


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
