from sqlalchemy import select

from app.models import BalanceEntry, Student
from app.modules.imports.steps import IMPORT_MONEY_NOTES
from app.services import balance as bal
from tests.conftest import login, make_staff
from tests.test_core_learning import YANGI, _setup, _student


async def test_student_history_shows_groups_transfer_and_status(db, client, owner_h):
    bid, teacher, room, g = await _setup(db, client, owner_h)
    s = await _student(db, client, owner_h, bid)
    assert (await client.post(f"/api/groups/{g['id']}/members", headers=owner_h, json={"student_id": s["id"]})).status_code == 201
    r = await client.post("/api/groups", headers=owner_h, json={
        "name": "EL-6", "branch_id": bid, "level_id": g["level_id"], "teacher_id": teacher.id, "room_id": room.id})
    g2 = r.json()
    r = await client.post(f"/api/students/{s['id']}/transfer", headers=owner_h, json={"to_group_id": g2["id"]})
    assert r.status_code == 200, r.text
    r = await client.patch(f"/api/students/{s['id']}", headers=owner_h, json={"status": "finished"})
    assert r.status_code == 200, r.text
    h = await client.get(f"/api/students/{s['id']}/history", headers=owner_h)
    assert h.status_code == 200, h.text
    texts = [x["text"] for x in h.json()]
    assert any("Переведён из «EL-5» в «EL-6»" in x for x in texts)
    assert any("Закончил обучение" in x for x in texts)
    assert any("Начал заниматься в группе «EL-6»" in x for x in texts)
    assert any(x == "Добавлен в систему" for x in texts)


async def test_annul_imported_money(db, client, owner_h):
    from tests.conftest import branch_id
    bid = await branch_id(db, YANGI)
    a = await _student(db, client, owner_h, bid, "Импорт Один", "+77051112201")
    b = await _student(db, client, owner_h, bid, "Импорт Долг", "+77051112202")
    sa, sb = await db.get(Student, a["id"]), await db.get(Student, b["id"])
    await bal.apply(db, sa, "manual", money=10000, note=IMPORT_MONEY_NOTES[0])
    await bal.apply(db, sa, "manual", money=3000, note="Остаток после частичной оплаты")  # not from import
    await bal.apply(db, sb, "manual", money=-5000, note=IMPORT_MONEY_NOTES[0])
    await db.commit()
    office = await make_staff(db, "office_manager", [YANGI], "+77030000009")
    oh = await login(client, office.phone)
    assert (await client.post("/api/import/old-crm/annul-money", headers=oh)).status_code == 403
    p = await client.post("/api/import/old-crm/annul-money", headers=owner_h)
    assert p.status_code == 200, p.text
    assert p.json()["positive"] == {"students": 1, "sum": 10000} and p.json()["debts"] == {"students": 1, "sum": -5000}
    await db.refresh(sa)
    assert sa.money_balance == 13000  # preview changes nothing
    r = await client.post("/api/import/old-crm/annul-money?commit=true", headers=owner_h)
    assert r.status_code == 200, r.text
    await db.refresh(sa)
    await db.refresh(sb)
    assert sa.money_balance == 3000 and sb.money_balance == -5000  # debts kept unless asked
    r = await client.post("/api/import/old-crm/annul-money?commit=true&include_debts=true", headers=owner_h)
    assert r.json()["positive"]["students"] == 0
    await db.refresh(sb)
    assert sb.money_balance == 0
    n = len((await db.scalars(select(BalanceEntry).where(BalanceEntry.student_id == sa.id))).all())
    again = await client.post("/api/import/old-crm/annul-money?commit=true&include_debts=true", headers=owner_h)
    assert again.json()["positive"]["students"] == 0 and again.json()["debts"]["students"] == 0
    assert len((await db.scalars(select(BalanceEntry).where(BalanceEntry.student_id == sa.id))).all()) == n
    h = await client.get(f"/api/students/{sa.id}/history", headers=owner_h)
    assert any("Аннулирован остаток" in x["text"] for x in h.json())
