from datetime import timedelta

from sqlalchemy import select

from app.models import Accrual, Lesson, LeadStage, Pipeline
from app.services.clock import now, today
from tests.conftest import branch_id, level_id, login, make_staff
from tests.test_core_learning import YANGI, _setup, _student


async def test_expense_categories_without_code_rename_archive(db, client, owner_h):
    r = await client.post("/api/expense-categories", headers=owner_h, json={"name": "Канцтовары"})
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    assert (await client.post("/api/expense-categories", headers=owner_h, json={"name": "канцтовары"})).status_code == 400
    r = await client.patch(f"/api/expense-categories/{cid}", headers=owner_h, json={"name": "Канцелярия"})
    assert r.status_code == 200 and r.json()["name"] == "Канцелярия"
    assert (await client.post(f"/api/expense-categories/{cid}/archive", headers=owner_h)).status_code == 204
    names = [c["name"] for c in (await client.get("/api/expense-categories", headers=owner_h)).json()]
    assert "Канцелярия" not in names


async def test_lead_stages_add_order_archive(db, client, owner_h):
    p = await db.scalar(select(Pipeline).where(Pipeline.code == "main"))
    r = await client.post(f"/api/crm/pipelines/{p.id}/stages", headers=owner_h, json={"name": "Думает", "color": "#123456"})
    assert r.status_code == 201, r.text
    new = r.json()
    stages = (await client.get("/api/crm/pipelines", headers=owner_h)).json()[0]["stages"]
    assert not stages[-1]["system"] or stages[-1]["code"] in ("paid", "lost")
    assert any(s["id"] == new["id"] for s in stages)
    ids = [s["id"] for s in stages]
    ids.remove(new["id"])
    ids.insert(0, new["id"])
    r = await client.put(f"/api/crm/pipelines/{p.id}/order", headers=owner_h, json={"stage_ids": ids})
    assert r.status_code == 200 and r.json()[0]["id"] == new["id"]
    r = await client.patch(f"/api/crm/stages/{new['id']}", headers=owner_h, json={"name": "Думает 2", "color": "#123456"})
    assert r.json()["name"] == "Думает 2"
    sys_stage = await db.scalar(select(LeadStage).where(LeadStage.pipeline_id == p.id, LeadStage.code == "new"))
    assert (await client.post(f"/api/crm/stages/{sys_stage.id}/archive", headers=owner_h)).status_code == 400
    assert (await client.post(f"/api/crm/stages/{new['id']}/archive", headers=owner_h)).status_code == 204


async def test_level_archive_blocked_by_active_group(db, client, owner_h):
    bid, teacher, room, g = await _setup(db, client, owner_h)
    assert (await client.post(f"/api/levels/{g['level_id']}/archive", headers=owner_h)).status_code == 400


async def test_duo_group_capacity_kind_filter_and_teacher_rate(db, client, owner_h):
    bid = await branch_id(db, YANGI)
    teacher = await make_staff(db, "teacher", [YANGI], "+77020000011", "Дуэт Учитель")
    from app.models import Room

    room = await db.scalar(select(Room).where(Room.branch_id == bid).order_by(Room.id))
    r = await client.post("/api/groups", headers=owner_h, json={
        "name": "DUO-1", "branch_id": bid, "level_id": await level_id(db, "ELE"), "teacher_id": teacher.id,
        "room_id": room.id, "capacity": 12, "kind": "duo"})
    assert r.status_code == 201, r.text
    g = r.json()
    assert g["kind"] == "duo" and g["capacity"] == 2
    kinds = {x["kind"] for x in (await client.get("/api/groups?kind=duo", headers=owner_h)).json()}
    assert kinds == {"duo"}
    s = await _student(db, client, owner_h, bid, name="Дуэт Один", phone="+77051234001")
    await client.post(f"/api/groups/{g['id']}/members", headers=owner_h, json={"student_id": s["id"]})
    from app.models import GroupMember

    for m in await db.scalars(select(GroupMember).where(GroupMember.student_id == s["id"])):
        m.joined_on = today() - timedelta(days=30)
    lesson = Lesson(branch_id=bid, group_id=g["id"], level_id=g["level_id"], teacher_id=teacher.id, room_id=room.id,
                    starts_at=now() - timedelta(hours=2), ends_at=now() - timedelta(minutes=30))
    db.add(lesson)
    await db.commit()
    d = today().isoformat()
    ls = (await client.get(f"/api/lessons?from={d}&to={d}&kind=duo", headers=owner_h)).json()
    assert [x["kind"] for x in ls] == ["duo"]
    assert (await client.get(f"/api/lessons?from={d}&to={d}&kind=individual", headers=owner_h)).json() == []
    r = await client.put(f"/api/lessons/{lesson.id}/attendance", headers=owner_h,
                          json={"marks": [{"student_id": s["id"], "status": "present"}]})
    assert r.status_code == 200, r.text
    acc = await db.scalar(select(Accrual).where(Accrual.ref_type == "lesson", Accrual.ref_id == lesson.id))
    assert acc.amount == 2500


async def test_contract_number_unique(db, client, owner_h):
    bid = await branch_id(db, YANGI)
    r = await client.post("/api/students", headers=owner_h, json={
        "full_name": "Договор Один", "branch_id": bid, "contract_no": "D-15", "contract_date": today().isoformat()})
    assert r.status_code == 201, r.text
    assert r.json()["contract_no"] == "D-15"
    r = await client.post("/api/students", headers=owner_h, json={"full_name": "Договор Два", "branch_id": bid, "contract_no": "D-15"})
    assert r.status_code == 409
    r = await client.post("/api/students", headers=owner_h, json={"full_name": "Договор Два", "branch_id": bid})
    sid = r.json()["id"]
    assert (await client.patch(f"/api/students/{sid}", headers=owner_h, json={"contract_no": "D-15"})).status_code == 409
    assert (await client.patch(f"/api/students/{sid}", headers=owner_h, json={"contract_no": "D-16"})).status_code == 200


async def test_payment_edit_method_note_date(db, client, owner_h):
    bid, teacher, room, g = await _setup(db, client, owner_h)
    s = await _student(db, client, owner_h, bid)
    p = (await client.post("/api/payments", headers=owner_h, json={"student_id": s["id"], "lessons": 8, "method": "cash"})).json()
    past = (today() - timedelta(days=3)).isoformat()
    r = await client.patch(f"/api/payments/{p['id']}", headers=owner_h, json={"method": "kaspi", "note": "чек 15", "paid_on": past})
    assert r.status_code == 200, r.text
    assert r.json()["method"] == "kaspi" and r.json()["note"] == "чек 15"
    office = await make_staff(db, "office_manager", [YANGI], "+77020000012", "Офис Три")
    oh = await login(client, office.phone)
    r = await client.patch(f"/api/payments/{p['id']}", headers=oh, json={"paid_on": today().isoformat()})
    assert r.status_code == 403
    r = await client.patch(f"/api/payments/{p['id']}", headers=oh, json={"note": "ok"})
    assert r.status_code == 200


async def test_level_create_without_code_and_edit_price(db, client, owner_h):
    r = await client.post("/api/levels", headers=owner_h, json={"name": "Дуэт Elementary", "lesson_price": 4500})
    assert r.status_code == 201, r.text
    lv = r.json()
    r = await client.patch(f"/api/levels/{lv['id']}", headers=owner_h, json={"name": "Дуэт Elementary", "lesson_price": 5000})
    assert r.status_code == 200 and r.json()["lesson_price"] == 5000 and r.json()["code"] == lv["code"]
    assert (await client.post(f"/api/levels/{lv['id']}/archive", headers=owner_h)).status_code == 204
