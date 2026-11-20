from datetime import timedelta

from sqlalchemy import select

from app.models import Accrual, GroupMember, Lesson
from app.services.clock import local, today
from tests.conftest import branch_id, level_id, make_staff

YANGI = "Янги шахар"


async def test_group_entered_late_gets_its_past_lessons_and_members_from_the_first_day(client, db, owner_h):
    from tests.test_core_learning import _setup, _student

    bid, teacher, room, g = await _setup(db, client, owner_h)
    start = today() - timedelta(days=7)
    rule = {"weekdays": list(range(7)), "start_time": "07:00", "end_time": "07:30", "room_id": room.id}
    too_old = (today() - timedelta(days=40)).isoformat()
    assert (await client.post(f"/api/groups/{g['id']}/schedule", headers=owner_h, json={**rule, "valid_from": too_old})).status_code == 400
    r = await client.post(f"/api/groups/{g['id']}/schedule", headers=owner_h, json={**rule, "valid_from": start.isoformat()})
    assert r.status_code == 201, r.text
    assert r.json()["past"] == 7
    days = sorted(local(x.starts_at).date() for x in await db.scalars(select(Lesson).where(Lesson.group_id == g["id"])))
    assert days[0] == start and len(set(days)) == len(days)
    assert (await client.get(f"/api/groups/{g['id']}", headers=owner_h)).json()["starts_on"] == start.isoformat()

    s = await _student(db, client, owner_h, bid, "Задним Числом", "+77051116001")
    m = f"/api/groups/{g['id']}/members"
    early = (start - timedelta(days=1)).isoformat()
    assert (await client.post(m, headers=owner_h, json={"student_id": s["id"], "joined_on": early})).status_code == 400
    assert (await client.post(m, headers=owner_h, json={"student_id": s["id"], "joined_on": start.isoformat()})).status_code == 201
    assert (await db.scalar(select(GroupMember).where(GroupMember.student_id == s["id"]))).joined_on == start
    first = await db.scalar(select(Lesson).where(Lesson.group_id == g["id"]).order_by(Lesson.starts_at))
    roster = (await client.get(f"/api/lessons/{first.id}/attendance", headers=owner_h)).json()
    assert [x["student_id"] for x in roster["rows"]] == [s["id"]]


async def test_individual_lesson_is_not_paid_when_the_student_did_not_come(client, db, owner_h):
    from tests.test_core_learning import _lesson_now, _student

    bid = await branch_id(db, YANGI)
    teacher = await make_staff(db, "teacher", [YANGI], "+77051116010", "Индив Учитель")
    from app.models import Room
    room = await db.scalar(select(Room).where(Room.branch_id == bid).order_by(Room.id))
    g = (await client.post("/api/groups", headers=owner_h, json={
        "name": "Индив 1", "branch_id": bid, "level_id": await level_id(db, "ELE"), "teacher_id": teacher.id,
        "room_id": room.id, "kind": "individual"})).json()
    s = await _student(db, client, owner_h, bid, "Один Ученик", "+77051116011")
    await client.post(f"/api/groups/{g['id']}/members", headers=owner_h, json={"student_id": s["id"]})
    lesson = await _lesson_now(db, g, teacher, room)
    lid = lesson.id

    async def pay(status):
        r = await client.put(f"/api/lessons/{lid}/attendance", headers=owner_h,
                             json={"marks": [{"student_id": s["id"], "status": status}], "reason": "исправление"})
        assert r.status_code == 200, r.text
        a = await db.scalar(select(Accrual).where(Accrual.kind == "lesson", Accrual.ref_id == lid))
        if a:
            await db.refresh(a)
        return a.amount if a else 0

    assert await pay("absent") == 0
    assert await pay("present") == 2000
    assert await pay("excused") == 0


async def test_lead_can_be_corrected_and_becomes_a_student_only_in_the_paid_column(client, db, owner_h):
    from app.services.crm import stage_by_code

    bid = await branch_id(db, YANGI)
    lead = (await client.post("/api/crm/leads", headers=owner_h, json={"full_name": "87051116020", "branch_id": bid})).json()
    r = await client.patch(f"/api/crm/leads/{lead['id']}", headers=owner_h, json={"full_name": "Айдана", "phone": "87051116020"})
    assert r.status_code == 200 and r.json()["full_name"] == "Айдана" and r.json()["phone"] == "+77051116020"
    assert (await client.patch(f"/api/crm/leads/{lead['id']}", headers=owner_h, json={"full_name": " "})).status_code == 400
    assert (await client.post(f"/api/crm/leads/{lead['id']}/convert", headers=owner_h, json={})).status_code == 400
    paid = await stage_by_code(db, "main", "paid")
    assert (await client.post(f"/api/crm/leads/{lead['id']}/stage", headers=owner_h, json={"stage_id": paid.id})).status_code == 200
    r = await client.post(f"/api/crm/leads/{lead['id']}/convert", headers=owner_h, json={})
    assert r.status_code == 200 and r.json()["student_id"]
