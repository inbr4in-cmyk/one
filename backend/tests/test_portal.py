from datetime import timedelta

from app.models import Attendance, Homework, Lesson, Room, Student
from app.services.clock import now
from sqlalchemy import select
from tests.test_chats import _portal_login, _world


async def _held_lesson(db, g, teacher, students, status="present"):
    room = await db.scalar(select(Room).where(Room.branch_id == g["branch_id"]))
    lesson = Lesson(branch_id=g["branch_id"], group_id=g["id"], level_id=g["level_id"], teacher_id=teacher.id, room_id=room.id,
                    starts_at=now() - timedelta(days=1, hours=2), ends_at=now() - timedelta(days=1), status="done",
                    attendance_marked_at=now() - timedelta(days=1))
    db.add(lesson)
    await db.flush()
    for s in students:
        db.add(Attendance(lesson_id=lesson.id, student_id=s["id"], status=status, marked_by=teacher.id, grade=5, comment="Молодец"))
    await db.flush()
    return lesson


async def test_parent_sees_only_own_child_and_block(db, client, owner_h):
    _, teacher, g, (a, b) = await _world(db, client, owner_h)
    pa = await _portal_login(db, client, a["guardians"][0]["user_id"])
    me = (await client.get("/api/portal/me", headers=pa)).json()
    assert me["kind"] == "parent" and [c["id"] for c in me["children"]] == [a["id"]]
    assert me["children"][0]["groups"][0]["teacher_id"] == teacher.id
    assert (await client.get(f"/api/portal/students/{b['id']}/attendance", headers=pa)).status_code == 404
    lesson = await _held_lesson(db, g, teacher, [a])
    att = (await client.get(f"/api/portal/students/{a['id']}/attendance", headers=pa)).json()
    assert att["items"][0]["grade"] == 5 and att["items"][0]["comment"] == "Молодец"
    r = await client.post(f"/api/portal/lessons/{lesson.id}/rate", headers=pa, json={"student_id": a["id"], "stars": 5})
    assert r.status_code == 201
    # Staff can't use the cabinet
    assert (await client.get("/api/portal/me", headers=owner_h)).status_code == 403
    # Non-payment block: payments stay visible, the rest is closed
    st = await db.get(Student, a["id"])
    st.access_blocked_at = now()
    await db.flush()
    assert (await client.get(f"/api/portal/students/{a['id']}/attendance", headers=pa)).status_code == 403
    pay = (await client.get(f"/api/portal/students/{a['id']}/payments", headers=pa)).json()
    assert pay["blocked"] is True


async def test_student_homework_submit(db, client, owner_h):
    _, teacher, g, (a, b) = await _world(db, client, owner_h)
    h = Homework(group_id=g["id"], title="Workbook p.12", created_by=teacher.id)
    db.add(h)
    await db.flush()
    sa = await _portal_login(db, client, a["user_id"])
    pa = await _portal_login(db, client, a["guardians"][0]["user_id"])
    hw = (await client.get(f"/api/portal/students/{a['id']}/homework", headers=sa)).json()
    assert hw[0]["status"] == "assigned"
    assert (await client.post(f"/api/portal/homework/{h.id}/submit", headers=pa, json={"student_id": a["id"], "answer": "x"})).status_code == 403
    r = await client.post(f"/api/portal/homework/{h.id}/submit", headers=sa, json={"student_id": a["id"], "answer": "Done: 1b 2a 3c"})
    assert r.json()["status"] == "submitted"
    sb = await _portal_login(db, client, b["user_id"])
    assert (await client.post(f"/api/portal/homework/{h.id}/submit", headers=sb, json={"student_id": a["id"], "answer": "x"})).status_code == 404
