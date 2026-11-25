"""Owner's request of 25.11.2026: lesson plan of a level, picked when marking attendance, test alerts."""
from datetime import time, timedelta

from sqlalchemy import select

from app.models import Lesson, Level, Notification
from app.services import plan
from app.services.clock import at_local, today
from tests.conftest import make_staff
from tests.test_core_learning import _setup, _student

YANGI = "Янги шахар"


async def test_level_plan_is_picked_at_attendance_shown_ahead_and_warns_before_a_test(client, db, owner_h):
    bid, teacher, room, g = await _setup(db, client, owner_h)
    tid, rid, gid, lvl = teacher.id, room.id, g["id"], g["level_id"]
    (await db.get(Level, lvl)).name = "Elementary"
    await db.flush()
    assert "filled 46 rows" in await plan.seed(db)
    assert "already has 46 rows" in await plan.seed(db)
    rows = (await client.get(f"/api/levels/{lvl}/plan", headers=owner_h)).json()
    assert len(rows) == 46 and rows[14]["kind"] == "progress_test" and rows[14]["month"] == 2 and rows[14]["num"] == 3
    assert rows[45]["kind"] == "final_test" and rows[0]["title"].startswith("1A Grammar Bank")
    # the plan is edited in «Справочники»: a row renamed, one removed, one added
    body = {"rows": [{**rows[0], "title": "1A Grammar Bank (new)"}, *rows[2:], {"month": 4, "title": "Extra", "kind": "lesson"}]}
    r = await client.put(f"/api/levels/{lvl}/plan", headers=owner_h, json=body)
    assert r.status_code == 200 and len(r.json()) == 46 and r.json()[0]["title"].endswith("(new)") and r.json()[0]["id"] == rows[0]["id"]
    rows = r.json()
    meth = await make_staff(db, "branch_admin", [YANGI], "+77052227401", "Методист План")
    from app.models import Role, UserRole
    role = Role(code="methodist_t", name="Методист")
    db.add(role)
    await db.flush()
    db.add(UserRole(user_id=meth.id, role_id=role.id))
    meth_id = meth.id
    sid = (await _student(db, client, owner_h, bid, "План Урок", "+77052227402"))["id"]
    await client.post(f"/api/groups/{gid}/members", headers=owner_h, json={"student_id": sid, "joined_on": (today() - timedelta(days=9)).isoformat()})
    ids = []
    for back in (3, 2, 1, -1, -2):
        d = today() - timedelta(days=back)
        x = Lesson(branch_id=bid, group_id=gid, level_id=lvl, teacher_id=tid, room_id=rid,
                   starts_at=at_local(d, time(15, 0)), ends_at=at_local(d, time(16, 0)))
        db.add(x)
        await db.flush()
        ids.append(x.id)
    await db.commit()

    async def week():
        r = await client.get(f"/api/lessons?from={today() - timedelta(days=3)}&to={today() + timedelta(days=2)}", headers=owner_h)
        return {x["id"]: x for x in r.json()}

    w = await week()  # a group that has not held a lesson starts from the first row
    assert [w[i]["plan_no"] for i in ids] == [1, 2, 3, 4, 5] and all(w[i]["plan_guess"] for i in ids)
    marks = {"marks": [{"student_id": sid, "status": "present"}], "reason": "позже"}
    r = await client.put(f"/api/lessons/{ids[0]}/attendance", headers=owner_h, json=marks)
    assert r.status_code == 400 and "по плану" in r.text  # the plan lesson is required
    assert (await client.put(f"/api/lessons/{ids[0]}/attendance", headers=owner_h, json={**marks, "plan_item_id": 999999})).status_code == 400
    ro = (await client.get(f"/api/lessons/{ids[0]}/attendance", headers=owner_h)).json()
    assert len(ro["plan"]) == 46 and ro["lesson"]["plan_item_id"] == rows[0]["id"] and ro["lesson"]["plan_guess"] is True
    # the group is already at lesson 13: the teacher picks it, the coming lessons follow from there
    r = await client.put(f"/api/lessons/{ids[0]}/attendance", headers=owner_h, json={**marks, "plan_item_id": rows[11]["id"]})
    assert r.status_code == 200 and r.json()["lesson"]["plan_no"] == 12 and r.json()["lesson"]["plan_guess"] is False
    assert not list(await db.scalars(select(Notification).where(Notification.user_id == meth_id, Notification.title.like("%Progress Test%"))))
    w = await week()
    assert [w[i]["plan_no"] for i in ids] == [12, 13, 14, 15, 16] and w[ids[3]]["plan_kind"] == "progress_test"
    # a correction without picking again keeps the row; the lesson before the test tells the methodist
    assert (await client.put(f"/api/lessons/{ids[0]}/attendance", headers=owner_h, json=marks)).status_code == 200
    assert (await client.put(f"/api/lessons/{ids[1]}/attendance", headers=owner_h, json={**marks, "plan_item_id": rows[12]["id"]})).status_code == 200
    for _ in range(2):  # re-saving does not repeat the alert
        r = await client.put(f"/api/lessons/{ids[2]}/attendance", headers=owner_h, json={**marks, "plan_item_id": rows[13]["id"]})
        assert r.status_code == 200, r.text
    notes = list(await db.scalars(select(Notification).where(Notification.user_id == meth_id, Notification.title.like("%Progress Test%"))))
    assert len(notes) == 1 and "Progress Test 1 Day 1" in notes[0].title and "Дана Учитель" in notes[0].body
