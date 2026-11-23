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
