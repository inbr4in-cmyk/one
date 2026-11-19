from datetime import timedelta

from sqlalchemy import select

from app.models import Accrual, Expense, StaffPayout
from app.services.clock import now, period_of, today
from tests.conftest import branch_id, login, make_staff

YANGI = "Янги шахар"


async def test_settle_with_staff_by_parts_goes_to_expenses_and_may_leave_a_debt(client, db, owner_h):
    from tests.test_core_learning import _lesson_now, _setup, _student

    bid, teacher, room, g = await _setup(db, client, owner_h)
    ids = []
    for i in range(7):
        s = await _student(db, client, owner_h, bid, f"Расчёт {i}", f"+7705111550{i}")
        await client.post(f"/api/groups/{g['id']}/members", headers=owner_h, json={"student_id": s["id"]})
        ids.append(s["id"])
    lesson = await _lesson_now(db, g, teacher, room)
    await client.put(f"/api/lessons/{lesson.id}/attendance", headers=owner_h,
                     json={"marks": [{"student_id": i, "status": "present"} for i in ids]})
    period = period_of(today())
    q = f"/api/payroll/settlement?user_id={teacher.id}&branch_id={bid}&period={period}"
    st = (await client.get(q, headers=owner_h)).json()
    parts = {p["part"]: p for p in st["parts"]}
    assert parts["rate"]["left"] == 2500 and parts["kpi"]["left"] == 200 and st["balance"] == 2700

    # only the lesson rate is paid, with a bonus and a fine written in the same payment
    r = await client.post("/api/payroll/payouts", headers=owner_h, json={
        "user_id": teacher.id, "branch_id": bid, "period": period, "lines": [{"part": "rate", "amount": 2500}],
        "bonus": {"amount": 1000, "note": "За открытый урок"}, "fine": {"amount": 300, "note": "Опоздание"}})
    assert r.status_code == 201, r.text
    parts = {p["part"]: p for p in r.json()["parts"]}
    assert parts["rate"]["left"] == 0 and parts["kpi"]["left"] == 200
    assert parts["bonus"] == {**parts["bonus"], "accrued": 1000, "paid": 1000, "left": 0}
    assert parts["deduction"]["accrued"] == -300 and parts["deduction"]["left"] == 0
    assert r.json()["balance"] == 200 and r.json()["payouts"][0]["total"] == 3200
    exp = await db.scalar(select(Expense).where(Expense.source_ref.like("payout:%")))
    assert exp.amount == 3200 and exp.branch_id == bid and "Зарплата" in exp.note
    sheet = (await client.get(f"/api/payroll?period={period}&branch_id={bid}", headers=owner_h)).json()
    me = next(p for p in sheet["people"] if p["user_id"] == teacher.id)
    assert me["paid"] == 3200 and me["left"] == 200
    # the P&L counts the pay as it is earned, the payout does not come on top of it
    d = today().isoformat()
    pnl = (await client.get(f"/api/finance/pnl?date_from={d}&date_to={d}", headers=owner_h)).json()
    row = next(x for x in pnl["branches"] if x["branch_id"] == bid)
    assert row["expenses"] == {} and row["payroll"] == 3400

    # an advance: more than earned → the person's debt
    r = await client.post("/api/payroll/payouts", headers=owner_h, json={
        "user_id": teacher.id, "branch_id": bid, "period": period, "lines": [{"part": "kpi", "amount": 5200}]})
    assert r.status_code == 201 and r.json()["balance"] == -5000
    # a teacher cannot pay anybody
    th = await login(client, teacher.phone)
    assert (await client.post("/api/payroll/payouts", headers=th, json={
        "user_id": teacher.id, "branch_id": bid, "lines": [{"part": "rate", "amount": 1}]})).status_code == 403
    mine = (await client.get(f"/api/payroll/my?period={period}", headers=th)).json()
    assert mine["paid"] == 8400 and len(mine["payouts"]) == 2
    # a payment entered by mistake is cancelled together with its expense
    batch = r.json()["payouts"][0]["id"]
    assert (await client.post(f"/api/payroll/payouts/{batch}/cancel", headers=owner_h, json={})).status_code == 200
    st = (await client.get(q, headers=owner_h)).json()
    assert st["balance"] == 200 and len(st["payouts"]) == 1
    left = (await db.scalars(select(Expense).where(Expense.source_ref.like("payout:%"), Expense.archived_at.is_(None)))).all()
    assert len(left) == 1
