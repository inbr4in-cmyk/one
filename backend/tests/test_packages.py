from sqlalchemy import select

from app.models import Payment
from tests.conftest import branch_id

YANGI = "Янги шахар"


async def test_package_sale_adds_lessons_and_end_date(db, client, owner_h):
    r = await client.post("/api/packages", headers=owner_h, json={"name": "3 месяца", "months": 3, "price": 90000, "lessons": 36})
    assert r.status_code == 201, r.text
    pkg = r.json()
    assert [p["name"] for p in (await client.get("/api/packages", headers=owner_h)).json()] == ["3 месяца"]
    bid = await branch_id(db, YANGI)
    # A student without a level can still buy a subscription
    s = (await client.post("/api/students", headers=owner_h, json={"full_name": "Абонемент Тест", "phone": "+77051230077", "branch_id": bid})).json()
    q = await client.post("/api/payments/quote", headers=owner_h, json={"student_id": s["id"], "package_id": pkg["id"], "method": "kaspi"})
    assert q.status_code == 200, q.text
    assert q.json()["to_pay"] == 90000 and q.json()["lessons"] == 36 and q.json()["lesson_price"] == 2500
    r = await client.post("/api/payments", headers=owner_h, json={"student_id": s["id"], "package_id": pkg["id"], "method": "kaspi"})
    assert r.status_code == 201, r.text
    p = await db.get(Payment, r.json()["id"])
    assert p.amount == 90000 and p.lessons == 36 and p.package_id == pkg["id"] and p.valid_to is not None
    card = (await client.get(f"/api/students/{s['id']}", headers=owner_h)).json()
    assert card["balance"]["lessons_left"] == 36
    assert card["subscription"]["name"] == "3 месяца"
    # Editing changes new sales only; archive hides the package
    r = await client.patch(f"/api/packages/{pkg['id']}", headers=owner_h, json={"name": "3 месяца", "months": 3, "price": 95000, "lessons": 36})
    assert r.status_code == 200 and (await db.get(Payment, p.id)).amount == 90000
    assert (await client.post(f"/api/packages/{pkg['id']}/archive", headers=owner_h)).status_code == 204
    assert (await client.get("/api/packages", headers=owner_h)).json() == []
    r = await client.post("/api/payments/quote", headers=owner_h, json={"student_id": s["id"], "package_id": pkg["id"], "method": "kaspi"})
    assert r.status_code == 404
