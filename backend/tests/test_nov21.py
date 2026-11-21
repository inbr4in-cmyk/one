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
