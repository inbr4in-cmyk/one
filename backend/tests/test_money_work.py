from datetime import timedelta

from sqlalchemy import select

from app import jobs
from app.models import AuditLog, ExpenseCategory, Notification, Task
from app.services.clock import now, period_of, today
from tests.conftest import branch_id, login, make_staff
from tests.test_core_learning import _student

YANGI, SEVER = "Янги шахар", "Север"


async def _pay(client, h, sid, lessons=8):
    r = await client.post("/api/payments", headers=h, json={"student_id": sid, "lessons": lessons, "method": "kaspi"})
    assert r.status_code == 201, r.text
    return r.json()


async def test_pnl_shares_network_expenses_and_branch_admin_scope(db, client, owner_h):
    y, s = await branch_id(db, YANGI), await branch_id(db, SEVER)
    st = await _student(db, client, owner_h, y)
    p = await _pay(client, owner_h, st["id"])
    rent = await db.scalar(select(ExpenseCategory.id).where(ExpenseCategory.code == "rent"))
    ads = await db.scalar(select(ExpenseCategory.id).where(ExpenseCategory.code == "ads"))
    d = today().isoformat()
    assert (await client.post("/api/expenses", headers=owner_h, json={"branch_id": y, "category_id": rent, "amount": 5000, "spent_on": d})).status_code == 201
    assert (await client.post("/api/expenses", headers=owner_h, json={"branch_id": None, "category_id": ads, "amount": 10000, "spent_on": d})).status_code == 201
    rep = (await client.get("/api/finance/pnl", headers=owner_h)).json()
    yr = next(b for b in rep["branches"] if b["branch_id"] == y)
    sr = next(b for b in rep["branches"] if b["branch_id"] == s)
    # All revenue is in Янги шахар → it carries the whole network ad spend
    assert yr["net_revenue"] == p["amount"] and yr["expenses"] == {"Аренда": 5000, "Реклама": 10000}
    assert sr["expenses"] == {} and rep["total"]["profit"] == p["amount"] - 15000 - rep["total"]["payroll"]

    admin = await make_staff(db, "branch_admin", [SEVER], "+77020000050", "Админ Север")
    ah = await login(client, admin.phone)
    rep2 = (await client.get("/api/finance/pnl", headers=ah)).json()
    assert [b["branch_id"] for b in rep2["branches"]] == [s]
    assert (await client.get(f"/api/finance/pnl?branch_id={y}", headers=ah)).status_code == 403
    # Branch admin can't book a shared network expense
    r = await client.post("/api/expenses", headers=ah, json={"branch_id": None, "category_id": ads, "amount": 1, "spent_on": d})
    assert r.status_code == 400
    dash = (await client.get("/api/dashboard", headers=owner_h)).json()
    assert dash["revenue_month"] >= p["amount"] and dash["students_active"] >= 1 and len(dash["revenue_trend"]) == 6

    x = await client.get(f"/api/finance/export/payments.xlsx?period={period_of(today())}", headers=owner_h)
    assert x.status_code == 200 and x.content[:2] == b"PK"
    assert await db.scalar(select(AuditLog).where(AuditLog.action == "finance.export"))


async def test_payroll_adjust_approve_lock_and_own_scope(db, client, owner_h):
    y = await branch_id(db, YANGI)
    teacher = await make_staff(db, "teacher", [YANGI], "+77020000051", "Учитель")
    other = await make_staff(db, "teacher", [YANGI], "+77020000052", "Другой")
    r = await client.post("/api/payroll/adjust", headers=owner_h, json={
        "user_id": teacher.id, "branch_id": y, "kind": "bonus", "amount": 5000, "description": "Лучший урок месяца"})
    assert r.status_code == 201, r.text
    await client.post("/api/payroll/adjust", headers=owner_h, json={
        "user_id": other.id, "branch_id": y, "kind": "deduction", "amount": 1000, "description": "Опоздание"})
    th = await login(client, teacher.phone)
    my = (await client.get("/api/payroll/my", headers=th)).json()
    assert my["total"] == 5000
    sheet = (await client.get("/api/payroll", headers=th)).json()
    assert [p["user_id"] for p in sheet["people"]] == [teacher.id]  # own scope: nobody else's pay
    assert (await client.post("/api/payroll/adjust", headers=th, json={
        "user_id": teacher.id, "branch_id": y, "kind": "bonus", "amount": 1, "description": "себе"})).status_code == 403
    assert (await client.get("/api/payroll", headers=owner_h)).json()["total"] == 4000

    prev = period_of(today().replace(day=1) - timedelta(days=1))
    await client.post("/api/payroll/adjust", headers=owner_h, json={
        "user_id": teacher.id, "branch_id": y, "kind": "bonus", "amount": 700, "description": "За прошлый", "period": prev})
    r = await client.post("/api/payroll/periods/approve", headers=owner_h, json={"period": prev, "branch_id": y})
    assert r.status_code == 200 and r.json()["total"] == 700
    r = await client.post("/api/payroll/adjust", headers=owner_h, json={
        "user_id": teacher.id, "branch_id": y, "kind": "bonus", "amount": 1, "description": "поздно", "period": prev})
    assert r.status_code == 409
    assert (await client.post("/api/payroll/periods/approve", headers=owner_h,
                              json={"period": period_of(today()), "branch_id": y})).status_code == 400
    assert (await client.post("/api/payroll/periods/paid", headers=owner_h, json={"period": prev, "branch_id": y})).json()["status"] == "paid"


async def test_tasks_flow_and_recurring(db, client, owner_h):
    y = await branch_id(db, YANGI)
    om = await make_staff(db, "office_manager", [YANGI], "+77020000053", "Офис")
    r = await client.post("/api/tasks", headers=owner_h, json={
        "title": "Обзвонить должников", "branch_id": y, "assignee_ids": [om.id], "priority": "high",
        "due_at": (now() - timedelta(minutes=5)).isoformat()})
    assert r.status_code == 201, r.text
    t = r.json()
    assert t["overdue"] is True
    oh = await login(client, om.phone)
    mine = (await client.get("/api/tasks", headers=oh)).json()
    assert [x["id"] for x in mine["items"]] == [t["id"]]
    # Assignee can't rename, can move to review; creator closes
    assert (await client.patch(f"/api/tasks/{t['id']}", headers=oh, json={"title": "иначе"})).status_code == 403
    assert (await client.patch(f"/api/tasks/{t['id']}", headers=oh, json={"status": "cancelled"})).status_code == 403
    assert (await client.patch(f"/api/tasks/{t['id']}", headers=oh, json={"status": "review"})).json()["status"] == "review"
    assert (await client.post(f"/api/tasks/{t['id']}/comments", headers=oh, json={"text": "Обзвонила 12 из 14"})).status_code == 201
    owner_notes = (await db.scalars(select(Notification).where(Notification.kind == "task", Notification.user_id == t["creator_id"]))).all()
    assert len(owner_notes) == 2
    assert (await client.patch(f"/api/tasks/{t['id']}", headers=owner_h, json={"status": "done"})).json()["done_at"]

    r = await client.post("/api/tasks", headers=owner_h, json={
        "title": "Отчёт за день", "branch_id": y, "assignee_ids": [om.id], "recurrence": "daily"})
    out = await jobs.nightly(db)
    assert out["tasks"] == 1 and (await jobs.nightly(db))["tasks"] == 0
    copy = await db.scalar(select(Task).where(Task.parent_task_id == r.json()["id"]))
    assert copy.title == "Отчёт за день" and copy.due_at is not None

