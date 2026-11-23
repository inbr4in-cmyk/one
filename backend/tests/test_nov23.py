"""Owner's requests of 23.11.2026: moved lessons, «Работать как», who is told about absences."""
from datetime import time, timedelta

from sqlalchemy import select

from app.models import Lesson, Role, ScheduleRule, Task, UserRole
from app.services.clock import at_local, now, today
from tests.conftest import branch_id, login, make_staff
from tests.test_core_learning import _setup, _student

YANGI = "Янги шахар"


async def test_lesson_moved_onto_a_day_with_a_lesson_is_marked_too_and_both_show_where_they_went(client, db, owner_h):
    bid, teacher, room, g = await _setup(db, client, owner_h)
    tid, rid, gid = teacher.id, room.id, g["id"]
    sid = (await _student(db, client, owner_h, bid, "Два Урока", "+77052227301"))["id"]
    day = today() - timedelta(days=2)
    await client.post(f"/api/groups/{gid}/members", headers=owner_h, json={"student_id": sid, "joined_on": (day - timedelta(days=5)).isoformat()})
    rule = ScheduleRule(group_id=gid, weekdays=[0, 1, 2, 3, 4, 5, 6], start_time=time(15, 0), end_time=time(16, 0), room_id=rid,
                        teacher_id=tid, valid_from=day - timedelta(days=30))
    db.add(rule)
    await db.flush()
    own = Lesson(branch_id=bid, group_id=gid, level_id=g["level_id"], teacher_id=tid, room_id=rid, rule_id=rule.id,
                 starts_at=at_local(day, time(15, 0)), ends_at=at_local(day, time(16, 0)))
    prev = Lesson(branch_id=bid, group_id=gid, level_id=g["level_id"], teacher_id=tid, room_id=rid, rule_id=rule.id,
                  starts_at=at_local(day - timedelta(days=1), time(15, 0)), ends_at=at_local(day - timedelta(days=1), time(16, 0)))
    db.add_all([own, prev])
    await db.flush()
    own_id, prev_id = own.id, prev.id
    await db.commit()
    r = await client.post(f"/api/lessons/{prev_id}/move", headers=owner_h, json={
        "starts_at": at_local(day, time(17, 0)).isoformat(), "ends_at": at_local(day, time(18, 0)).isoformat(), "reason": "учитель болел"})
    assert r.status_code == 200, r.text
    moved = r.json()
    assert moved["moved_from_id"] == prev_id and moved["moved_from_at"]
    marks = {"marks": [{"student_id": sid, "status": "present"}], "reason": "позже"}
    assert (await client.put(f"/api/lessons/{moved['id']}/attendance", headers=owner_h, json=marks)).status_code == 200
    r = await client.put(f"/api/lessons/{own_id}/attendance", headers=owner_h, json=marks)
    assert r.status_code == 200, r.text  # two real lessons that day: no «уже отмечен»
    rows = (await client.get(f"/api/lessons?from={day - timedelta(days=1)}&to={day}&include_cancelled=true", headers=owner_h)).json()
    old = next(x for x in rows if x["id"] == prev_id)
    assert old["status"] == "cancelled" and old["moved_to_id"] == moved["id"] and old["moved_to_at"]
    assert (await client.put(f"/api/lessons/{prev_id}/attendance", headers=owner_h, json=marks)).status_code == 400


async def test_two_absences_alert_only_without_a_good_reason(client, db, owner_h):
    bid, teacher, room, g = await _setup(db, client, owner_h)
    sid = (await _student(db, client, owner_h, bid, "Пропуск Причина", "+77052227302"))["id"]
    await client.post(f"/api/groups/{g['id']}/members", headers=owner_h, json={"student_id": sid, "joined_on": (today() - timedelta(days=9)).isoformat()})
    ids = []
    for back in (4, 3, 2, 1):
        x = Lesson(branch_id=bid, group_id=g["id"], level_id=g["level_id"], teacher_id=teacher.id, room_id=room.id,
                   starts_at=now() - timedelta(days=back), ends_at=now() - timedelta(days=back) + timedelta(hours=1))
        db.add(x)
        await db.flush()
        ids.append(x.id)
    await db.commit()

    async def mark(lid, st):
        r = await client.put(f"/api/lessons/{lid}/attendance", headers=owner_h, json={"marks": [{"student_id": sid, "status": st}], "reason": "позже"})
        assert r.status_code == 200, r.text
        return len(list(await db.scalars(select(Task).where(Task.auto_kind == "absence2", Task.link_id == sid))))

    assert await mark(ids[0], "excused") == 0
    assert await mark(ids[1], "excused") == 0   # twice with a good reason: nobody is alerted
    assert await mark(ids[2], "absent") == 0    # one without a reason after an excused one
    assert await mark(ids[3], "absent") == 1    # two in a row without a reason


async def test_staff_with_two_roles_picks_the_one_to_work_in(client, db, owner_h):
    u = await make_staff(db, "teacher", [YANGI], "+77052227303", "Две Роли")
    role = await db.scalar(select(Role).where(Role.code == "branch_admin"))
    db.add(UserRole(user_id=u.id, role_id=role.id))
    await db.commit()
    h = await login(client, "+77052227303")
    me = (await client.get("/api/auth/me", headers=h)).json()
    assert {r["code"] for r in me["all_roles"]} == {"teacher", "branch_admin"} and me["active_role"] is None
    assert "payments.create" in me["permissions"]
    assert (await client.post("/api/auth/active-role", headers=h, json={"role": "owner"})).status_code == 400
    assert (await client.post("/api/auth/active-role", headers=h, json={"role": "teacher"})).status_code == 204
    me = (await client.get("/api/auth/me", headers=h)).json()
    assert me["roles"] == ["teacher"] and me["active_role"] == "teacher" and "payments.create" not in me["permissions"]
    assert (await client.get("/api/payments", headers=h)).status_code == 403
    assert (await client.post("/api/auth/active-role", headers=h, json={"role": None})).status_code == 204
    assert "payments.create" in (await client.get("/api/auth/me", headers=h)).json()["permissions"]


async def test_group_is_finished_with_a_past_date(client, db, owner_h):
    from app.models import GroupMember

    bid, teacher, room, g = await _setup(db, client, owner_h)
    tid, rid, gid = teacher.id, room.id, g["id"]
    sid = (await _student(db, client, owner_h, bid, "Финиш Дата", "+77052227311"))["id"]
    await client.post(f"/api/groups/{gid}/members", headers=owner_h, json={"student_id": sid, "joined_on": (today() - timedelta(days=20)).isoformat()})
    rule = ScheduleRule(group_id=gid, weekdays=[0, 1, 2, 3, 4, 5, 6], start_time=time(15, 0), end_time=time(16, 0), room_id=rid,
                        teacher_id=tid, valid_from=today() - timedelta(days=30))
    db.add(rule)
    await db.flush()
    ids = {}
    for back in (5, 2, 1, -1):
        d = today() - timedelta(days=back)
        x = Lesson(branch_id=bid, group_id=gid, level_id=g["level_id"], teacher_id=tid, room_id=rid, rule_id=rule.id,
                   starts_at=at_local(d, time(15, 0)), ends_at=at_local(d, time(16, 0)))
        db.add(x)
        await db.flush()
        ids[back] = x.id
    rule_id = rule.id
    await db.commit()
    marks = {"marks": [{"student_id": sid, "status": "present"}], "reason": "позже"}
    assert (await client.put(f"/api/lessons/{ids[2]}/attendance", headers=owner_h, json=marks)).status_code == 200
    fin = today() - timedelta(days=3)
    r = await client.post(f"/api/groups/{gid}/archive", headers=owner_h, json={"finished_on": fin.isoformat()})
    assert r.status_code == 409 and "проведённые уроки" in r.text  # a lesson was held after that day
    assert (await client.post(f"/api/groups/{gid}/archive", headers=owner_h,
                              json={"finished_on": (today() + timedelta(days=1)).isoformat()})).status_code == 400
    fin = today() - timedelta(days=2)
    r = await client.post(f"/api/groups/{gid}/archive", headers=owner_h, json={"finished_on": fin.isoformat()})
    assert r.status_code == 204, r.text
    db.expire_all()
    assert (await db.get(Lesson, ids[5])).status == "planned" and (await db.get(Lesson, ids[2])).status != "cancelled"
    assert (await db.get(Lesson, ids[1])).status == "cancelled" and (await db.get(Lesson, ids[-1])).status == "cancelled"
    assert (await db.get(ScheduleRule, rule_id)).valid_to == fin
    m = await db.scalar(select(GroupMember).where(GroupMember.group_id == gid, GroupMember.student_id == sid))
    assert m.left_on == fin + timedelta(days=1)


async def test_individual_lesson_of_a_frozen_student_is_closed(client, db, owner_h):
    from app.models import Group

    bid, teacher, room, g = await _setup(db, client, owner_h)
    tid, rid, gid = teacher.id, room.id, g["id"]
    (await db.get(Group, gid)).kind = "individual"
    sid = (await _student(db, client, owner_h, bid, "Индив Заморозка", "+77052227312"))["id"]
    await client.post(f"/api/groups/{gid}/members", headers=owner_h, json={"student_id": sid, "joined_on": (today() - timedelta(days=20)).isoformat()})
    d = today() - timedelta(days=1)
    ids = []
    for day in (d, d - timedelta(days=6)):
        x = Lesson(branch_id=bid, group_id=gid, level_id=g["level_id"], teacher_id=tid, room_id=rid,
                   starts_at=at_local(day, time(15, 0)), ends_at=at_local(day, time(16, 0)))
        db.add(x)
        await db.flush()
        ids.append(x.id)
    await db.commit()
    r = await client.post(f"/api/students/{sid}/freeze", headers=owner_h, json={
        "starts_on": str(today() - timedelta(days=3)), "ends_on": str(today() + timedelta(days=4)), "reason": "уехал"})
    assert r.status_code == 200, r.text
    rows = {x["id"]: x for x in (await client.get(f"/api/lessons?from={d - timedelta(days=6)}&to={d}", headers=owner_h)).json()}
    assert rows[ids[0]]["frozen"] is True and rows[ids[1]]["frozen"] is False
    marks = {"marks": [], "reason": "позже"}
    r = await client.put(f"/api/lessons/{ids[0]}/attendance", headers=owner_h, json=marks)
    assert r.status_code == 409 and "заморозке" in r.text
    marks = {"marks": [{"student_id": sid, "status": "present"}], "reason": "позже"}
    assert (await client.put(f"/api/lessons/{ids[1]}/attendance", headers=owner_h, json=marks)).status_code == 200


async def test_branch_admin_and_office_manager_get_no_trial_bonus(db):
    from app.services import retention

    adm = await make_staff(db, "branch_admin", [YANGI], "+77052227313", "Админ Без Пробного")
    off = await make_staff(db, "office_manager", [YANGI], "+77052227314", "Офис Без Пробного")
    sal = await make_staff(db, "sales", [YANGI], "+77052227315", "Продажи Пробный")
    both = await make_staff(db, "sales", [YANGI], "+77052227316", "Продажи И Офис")
    db.add(UserRole(user_id=both.id, role_id=(await db.scalar(select(Role).where(Role.code == "office_manager"))).id))
    await db.flush()
    assert [await retention.no_trial_bonus(db, u.id) for u in (adm, off, sal, both)] == [True, True, False, False]
