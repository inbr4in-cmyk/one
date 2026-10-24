from datetime import timedelta

from sqlalchemy import select

from app.models import Expense, Payment
from app.services.clock import now
from tests.conftest import branch_id, level_id, login, make_staff
from tests.test_chats import _portal_login, _world
from tests.test_core_learning import _student

YANGI, SEVER = "Янги шахар", "Север"


async def test_books_receive_sell_transfer(db, client, owner_h):
    y, s = await branch_id(db, YANGI), await branch_id(db, SEVER)
    b = (await client.post("/api/books", headers=owner_h, json={
        "title": "Elementary SB", "level_id": await level_id(db, "ELE"), "sale_price": 9000, "purchase_price": 6000})).json()
    r = await client.post("/api/books/receive", headers=owner_h, json={"branch_id": y, "book_id": b["id"], "qty": 10,
                                                                       "unit_price": 6000, "supplier": "Меломан"})
    assert r.json()["qty"] == 10
    assert await db.scalar(select(Expense).where(Expense.source_ref == f"book_in:{r.json()['id']}"))
    st = await _student(db, client, owner_h, y)
    assert (await client.get(f"/api/students/{st['id']}/books", headers=owner_h)).json()["needed"][0]["id"] == b["id"]
    r = await client.post("/api/books/sell", headers=owner_h, json={"student_id": st["id"], "book_id": b["id"], "method": "cash"})
    assert r.status_code == 201 and r.json()["left_in_stock"] == 9
    p = await db.get(Payment, r.json()["payment_id"])
    assert p.category == "book" and p.amount == 9000
    assert (await client.get(f"/api/students/{st['id']}/books", headers=owner_h)).json()["needed"] == []
    # Transfer: leaves Янги шахар now, arrives in Север only after confirmation
    t = (await client.post("/api/books/transfer", headers=owner_h, json={"from_branch_id": y, "to_branch_id": s,
                                                                       "book_id": b["id"], "qty": 3})).json()
    stock = {x["id"]: x["stock"] for x in (await client.get("/api/books", headers=owner_h)).json()}[b["id"]]
    assert stock[str(y)]["qty"] == 6
    admin_s = await make_staff(db, "branch_admin", [SEVER], "+77020000060")
    ah = await login(client, admin_s.phone)
    assert (await client.post(f"/api/books/transfers/{t['id']}/confirm", headers=ah)).json()["qty"] == 3
    assert (await client.post(f"/api/books/transfers/{t['id']}/confirm", headers=ah)).status_code == 409
    assert (await client.post("/api/books/writeoff", headers=owner_h, json={"branch_id": y, "book_id": b["id"], "qty": 100,
                                                                          "reason": "брак"})).status_code == 409
    rep = (await client.get("/api/books/report", headers=owner_h)).json()
    assert rep["totals"]["revenue"] == 9000 and rep["totals"]["profit"] == 3000


async def test_coins_limit_and_shop_order_cycle(db, client, owner_h):
    _, teacher, g, (a, b) = await _world(db, client, owner_h)
    th = await login(client, teacher.phone)
    r = await client.post("/api/coins/award", headers=th, json={"student_id": a["id"], "amount": 150, "reason": "Активность на уроке"})
    assert r.status_code == 201 and r.json()["limit_left"] == 50
    r = await client.post("/api/coins/award", headers=th, json={"student_id": a["id"], "amount": 60, "reason": "Ещё"})
    assert r.status_code == 409
    item = (await client.post("/api/shop/items", headers=owner_h, json={"name": "Кружка", "price_coins": 100, "stock": 1,
                                                                      "cost": 1500})).json()
    sa = await _portal_login(db, client, a["user_id"])
    sb = await _portal_login(db, client, b["user_id"])
    # Another student can't spend Алия's coins
    assert (await client.post("/api/shop/orders", headers=sb, json={"student_id": a["id"], "item_id": item["id"]})).status_code == 404
    o = await client.post("/api/shop/orders", headers=sa, json={"student_id": a["id"], "item_id": item["id"]})
    assert o.status_code == 201 and o.json()["balance"] == 50
    assert (await client.post("/api/shop/orders", headers=sa, json={"student_id": a["id"], "item_id": item["id"]})).status_code == 409
    oid = o.json()["id"]
    assert (await client.post(f"/api/shop/orders/{oid}/status", headers=sa, json={"status": "issued"})).status_code == 403
    assert (await client.post(f"/api/shop/orders/{oid}/status", headers=owner_h, json={"status": "issued"})).json()["status"] == "issued"
    assert await db.scalar(select(Expense).where(Expense.source_ref == f"shop_order:{oid}"))
    coins = (await client.get(f"/api/students/{a['id']}/coins", headers=owner_h)).json()
    assert coins["balance"] == 50
    top = (await client.get("/api/coins/top", headers=sa)).json()
    assert top[0]["student_id"] is None and " " not in top[0]["name"]


async def test_complaint_hidden_from_accused_and_deadlines(db, client, owner_h):
    _, teacher, g, (a, _) = await _world(db, client, owner_h)
    admin = await make_staff(db, "branch_admin", [YANGI], "+77020000061", "Админ")
    pa = await _portal_login(db, client, a["guardians"][0]["user_id"])
    r = await client.post("/api/complaints", headers=pa, json={
        "subject": "Учитель опоздал", "body": "Урок начался на 15 минут позже", "against_user_id": teacher.id})
    assert r.status_code == 201
    c = r.json()
    assert "author_id" not in c and "against_user_id" not in c
    ah = await login(client, admin.phone)
    assert [x["id"] for x in (await client.get("/api/complaints", headers=ah)).json()] == [c["id"]]
    # Even with complaints rights the accused would not see it
    from app.models import Role, UserRole
    role = await db.scalar(select(Role).where(Role.code == "branch_admin"))
    db.add(UserRole(user_id=teacher.id, role_id=role.id))
    await db.flush()
    th = await login(client, teacher.phone)
    assert (await client.get("/api/complaints", headers=th)).json() == []
    assert (await client.post(f"/api/complaints/{c['id']}", headers=th, json={"action": "answer", "answer": "Это неправда"})).status_code == 404

    r = await client.post(f"/api/complaints/{c['id']}", headers=ah, json={"action": "investigate"})
    assert r.json()["status"] == "investigating"
    r = await client.post(f"/api/complaints/{c['id']}", headers=ah, json={"action": "answer", "answer": "Провели беседу, урок продлён"})
    assert r.json()["status"] == "answered"
    assert (await client.post(f"/api/complaints/{c['id']}", headers=pa, json={"action": "appeal"})).json()["status"] == "appealed"
    assert (await client.post(f"/api/complaints/{c['id']}", headers=ah, json={"action": "close"})).status_code == 403
    mine = (await client.get("/api/complaints/my", headers=pa)).json()
    assert mine[0]["status"] == "appealed"


async def test_rules_versions_and_consent(db, client, owner_h):
    r = await client.post("/api/documents", headers=owner_h, json={
        "kind": "rules", "version": "1.0", "title": "Правила платформы", "body": "Текст правил платформы One English…",
        "effective_from": (now() - timedelta(days=1)).isoformat()})
    assert r.status_code == 201
    # A change must be announced 7 days ahead
    r = await client.post("/api/documents", headers=owner_h, json={
        "kind": "rules", "version": "1.1", "title": "Правила", "body": "Новая редакция правил…", "effective_from": now().isoformat()})
    assert r.status_code == 400
    doc = (await client.get("/api/documents/rules", headers=owner_h)).json()
    assert (await client.post("/api/consents", headers=owner_h, json={"document_id": doc["id"]})).status_code == 201
    assert (await client.get("/api/auth/me", headers=owner_h)).json()["rules_accepted_version"] == "1.0"
    # Staff can't sign the recording consent for somebody's child
    st = await _student(db, client, owner_h, await branch_id(db, YANGI))
    assert (await client.post("/api/consents", headers=owner_h, json={"document_id": doc["id"], "student_id": st["id"]})).status_code == 403


async def test_checkin_and_training(db, client, owner_h):
    om = await make_staff(db, "office_manager", [YANGI], "+77020000062", "Офис")
    oh = await login(client, om.phone)
    y = await branch_id(db, YANGI)
    assert (await client.post("/api/checkin", headers=oh, json={"branch_id": await branch_id(db, SEVER)})).status_code == 400
    assert (await client.post("/api/checkin", headers=oh, json={"branch_id": y})).status_code == 201
    assert (await client.post("/api/checkin", headers=oh, json={"branch_id": y})).status_code == 409
    assert (await client.post("/api/checkout", headers=oh)).json()["out_at"]
    assert (await client.put("/api/daily-report", headers=oh, json={"text": "Приняла 3 оплаты, обзвонила 10 лидов"})).status_code == 200
    assert len((await client.get("/api/daily-reports", headers=owner_h)).json()) == 1
    c = (await client.post("/api/training/courses", headers=owner_h, json={"title": "Курс офис-менеджера",
                                                                          "role_codes": ["office_manager"]})).json()
    t = (await client.post("/api/training/courses", headers=owner_h, json={"title": "Курс учителя", "role_codes": ["teacher"]})).json()
    m = (await client.post(f"/api/training/courses/{c['id']}/materials", headers=owner_h, json={
        "kind": "video", "title": "Как принять оплату", "url": "https://example.com/v"})).json()
    mine = (await client.get("/api/training/courses", headers=oh)).json()
    assert [x["id"] for x in mine] == [c["id"]]
    assert (await client.get(f"/api/training/courses/{t['id']}", headers=oh)).status_code == 404
    assert (await client.post(f"/api/training/materials/{m['id']}/done", headers=oh, json={})).status_code == 200
    prog = (await client.get("/api/training/progress", headers=owner_h)).json()
    row = next(p for p in prog if p["user_id"] == om.id)
    assert next(x for x in row["courses"] if x["course_id"] == c["id"])["done"] == 1

