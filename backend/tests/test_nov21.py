from datetime import timedelta

from sqlalchemy import select

from app.models import Lead, LeadEvent, Lesson, Room
from app.services.clock import now
from tests.conftest import branch_id, level_id, login, make_staff

YANGI = "Янги шахар"


async def test_admin_removes_a_wrong_history_line_and_a_wrong_trial_booking(client, db, owner_h):
    bid = await branch_id(db, YANGI)
    sales = await make_staff(db, "sales", [YANGI], "+77051117001", "Продажник")
    teacher = await make_staff(db, "teacher", [YANGI], "+77051117002", "Учитель")
    await db.commit()
    sh = await login(client, sales.phone)
    lead = (await client.post("/api/crm/leads", headers=sh, json={"full_name": "Ошибка Записи", "phone": "+77051117003", "branch_id": bid})).json()
    lid = lead["id"]
    ev = (await client.post(f"/api/crm/leads/{lid}/events", headers=sh, json={"kind": "note", "text": "не тот лид"})).json()
    assert (await client.delete(f"/api/crm/leads/{lid}/events/{ev['id']}", headers=sh)).status_code == 403  # sales cannot
    assert (await client.delete(f"/api/crm/leads/{lid}/events/{ev['id']}", headers=owner_h)).status_code == 204
    events = (await client.get(f"/api/crm/leads/{lid}", headers=owner_h)).json()["events"]
    assert all(e["id"] != ev["id"] for e in events)
    created = next(e for e in events if e["kind"] == "created")
    assert (await client.delete(f"/api/crm/leads/{lid}/events/{created['id']}", headers=owner_h)).status_code == 400

    g = (await client.post("/api/groups", headers=owner_h, json={"name": "TR-1", "branch_id": bid,
                                                                 "level_id": await level_id(db, "ELE"), "teacher_id": teacher.id})).json()
    room = await db.scalar(select(Room).where(Room.branch_id == bid))
    lesson = Lesson(branch_id=bid, group_id=g["id"], level_id=g["level_id"], teacher_id=teacher.id, room_id=room.id,
                    starts_at=now() + timedelta(days=1), ends_at=now() + timedelta(days=1, minutes=60))
    db.add(lesson)
    await db.flush()
    r = await client.post(f"/api/crm/leads/{lid}/trial", headers=sh, json={"lesson_id": lesson.id, "notify": False})
    assert r.status_code == 200, r.text
    assert (await client.delete(f"/api/crm/leads/{lid}/trial", headers=sh)).status_code == 403
    r = await client.delete(f"/api/crm/leads/{lid}/trial", headers=owner_h)
    assert r.status_code == 200, r.text
    assert r.json()["trial_lesson_id"] is None and r.json()["trial_at"] is None
    stages = {s["id"]: s["code"] for p in (await client.get("/api/crm/pipelines", headers=owner_h)).json() for s in p["stages"]}
    assert stages[r.json()["stage_id"]] == "contacted"
    texts = [e.text for e in await db.scalars(select(LeadEvent).where(LeadEvent.lead_id == lid))]
    assert not any((t or "").startswith("Записан на пробный") for t in texts)
    # and the lead can be booked again
    assert (await client.post(f"/api/crm/leads/{lid}/trial", headers=sh, json={"lesson_id": lesson.id, "notify": False})).status_code == 200
    assert (await db.get(Lead, lid)) is not None


async def test_one_excused_absence_a_month_is_free_and_the_next_is_charged(client, db, owner_h):
    from datetime import time

    from app.models import Accrual, Attendance, Student
    from app.services.clock import at_local, today
    from tests.test_core_learning import _student

    bid = await branch_id(db, YANGI)
    teacher = await make_staff(db, "teacher", [YANGI], "+77051117010", "Индив Учитель")
    room = await db.scalar(select(Room).where(Room.branch_id == bid).order_by(Room.id))
    g = (await client.post("/api/groups", headers=owner_h, json={
        "name": "Индив 2", "branch_id": bid, "level_id": await level_id(db, "ELE"), "teacher_id": teacher.id,
        "room_id": room.id, "kind": "individual"})).json()
    s = await _student(db, client, owner_h, bid, "Отпросился Дважды", "+77051117011")
    sid = s["id"]
    first = today().replace(day=1)
    await client.post(f"/api/groups/{g['id']}/members", headers=owner_h, json={"student_id": sid, "joined_on": max(first, today() - timedelta(days=30)).isoformat()})
    await client.post("/api/payments", headers=owner_h, json={"student_id": sid, "lessons": 8, "method": "cash"})
    days = [today() - timedelta(days=i) for i in (2, 1, 0)]
    if days[0].month != today().month:   # keep all three lessons in one month
        days = [today()] * 3
    ids = []
    for i, d in enumerate(days):
        x = Lesson(branch_id=bid, group_id=g["id"], level_id=g["level_id"], teacher_id=teacher.id, room_id=room.id,
                   starts_at=at_local(d, time(3 + i, 0)), ends_at=at_local(d, time(3 + i, 30)))
        db.add(x)
        await db.flush()
        ids.append(x.id)

    async def mark(lid, status):
        r = await client.put(f"/api/lessons/{lid}/attendance", headers=owner_h,
                             json={"marks": [{"student_id": sid, "status": status}], "reason": "исправление"})
        assert r.status_code == 200, r.text

    async def state():
        st = await db.get(Student, sid)
        await db.refresh(st)
        out = []
        for lid in ids:
            a = await db.scalar(select(Attendance).where(Attendance.lesson_id == lid))
            acc = await db.scalar(select(Accrual).where(Accrual.kind == "lesson", Accrual.ref_id == lid))
            if a:
                await db.refresh(a)
            if acc:
                await db.refresh(acc)
            out.append((a.charged if a else None, acc.amount if acc else None))
        return st.lessons_left, out

    await mark(ids[1], "excused")
    assert await state() == (8, [(None, None), (False, 0), (None, None)])
    await mark(ids[2], "excused")              # the second one this month is charged, the teacher gets the no-show rate
    assert await state() == (7, [(None, None), (False, 0), (True, 1000)])
    await mark(ids[0], "excused")              # an earlier lesson entered later takes the free place
    assert await state() == (6, [(False, 0), (True, 1000), (True, 1000)])
    await mark(ids[0], "present")              # he did come: the free absence goes back to the next one
    assert await state() == (6, [(True, 2000), (False, 0), (True, 1000)])
    await mark(ids[2], "absent")
    assert await state() == (6, [(True, 2000), (False, 0), (True, 1000)])


async def test_only_admin_and_methodist_move_lessons_and_set_substitutes(client, db, owner_h):
    from datetime import time

    from app.models import Role, UserRole
    from app.services.clock import at_local, today
    from tests.test_core_learning import _setup

    bid, teacher, room, g = await _setup(db, client, owner_h)
    day = today() + timedelta(days=3)
    x = Lesson(branch_id=bid, group_id=g["id"], level_id=g["level_id"], teacher_id=teacher.id, room_id=room.id,
               starts_at=at_local(day, time(3, 0)), ends_at=at_local(day, time(3, 30)))
    db.add(x)
    office = await make_staff(db, "office_manager", [YANGI], "+77051117020", "Офис")
    meth = await make_staff(db, "office_manager", [YANGI], "+77051117021", "Методист Филиала")
    role = Role(code="methodist_t", name="Методист")
    db.add(role)
    await db.flush()
    db.add(UserRole(user_id=meth.id, role_id=role.id))
    await db.commit()
    xid = x.id
    oh, mh = await login(client, office.phone), await login(client, meth.phone)
    body = {"starts_at": at_local(day, time(4, 0)).isoformat(), "ends_at": at_local(day, time(4, 30)).isoformat()}
    assert (await client.get("/api/lesson-rights", headers=oh)).json() == {"reschedule": False}
    assert (await client.post(f"/api/lessons/{xid}/move", headers=oh, json=body)).status_code == 403
    assert (await client.post(f"/api/lessons/{xid}/substitute", headers=oh, json={"teacher_id": teacher.id})).status_code == 403
    assert (await client.get("/api/lesson-rights", headers=mh)).json() == {"reschedule": True}
    r = await client.post(f"/api/lessons/{xid}/move", headers=mh, json=body)
    assert r.status_code == 200, r.text
