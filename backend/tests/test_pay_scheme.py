from datetime import date

from sqlalchemy import select

from app.models import Accrual
from app.services.clock import period_of, today
from app.services.payroll import accrue_once, accrue_salaries
from tests.conftest import make_staff

YANGI = "Янги шахар"


async def test_salary_scheme_accrues_monthly_salary_and_no_rates(db, client, owner_h):
    t = await make_staff(db, "teacher", [YANGI], "+77020000071", "Оклад Учитель")
    s = await make_staff(db, "teacher", [YANGI], "+77020000072", "Ставка Учитель")
    await db.commit()
    r = await client.patch(f"/api/staff/{t.id}", headers=owner_h, json={"salary": 200000, "pay_scheme": "salary"})
    assert r.status_code == 200, r.text
    assert r.json()["pay_scheme"] == "salary"
    period = period_of(today())
    # from Nov 2026 the salary follows the timesheet: mark one worked day
    bid = (await client.get("/api/branches", headers=owner_h)).json()
    bid = next(b["id"] for b in (bid["items"] if isinstance(bid, dict) else bid) if b["name"] == YANGI)
    r = await client.put("/api/payroll/timesheet", headers=owner_h, json={"user_id": t.id, "branch_id": bid,
                                                                       "days": [today().isoformat()], "status": "work"})
    assert r.status_code == 200, r.text
    from app.services.payroll import norm_days
    one_day = round(200000 / norm_days(period))
    sheet = (await client.get(f"/api/payroll?period={period}", headers=owner_h)).json()
    me = next(p for p in sheet["people"] if p["user_id"] == t.id)
    assert me["salary_total"] == one_day and me["rates_total"] == 0
    # оклад only: per-fact accruals are skipped; rates staff still get them
    assert not await accrue_once(db, user_id=t.id, kind="sale", amount=1000, ref=("payment", 1), on=today(),
                                 branch_id=None, description="x")
    assert await accrue_once(db, user_id=s.id, kind="sale", amount=1000, ref=("payment", 1), on=today(),
                             branch_id=None, description="x")
    # salary change follows into the open month, nightly doesn't duplicate
    await client.patch(f"/api/staff/{t.id}", headers=owner_h, json={"salary": 250000})
    await accrue_salaries(db)
    await db.commit()
    rows = (await db.scalars(select(Accrual).where(Accrual.user_id == t.id, Accrual.kind == "salary"))).all()
    assert [a.amount for a in rows] == [round(250000 / norm_days(period))]
    # switching back to rates removes the month's salary while the sheet is open
    await client.patch(f"/api/staff/{t.id}", headers=owner_h, json={"pay_scheme": "rates"})
    await db.refresh(rows[0])
    assert rows[0].amount == 0
    assert date.today()  # keep import used
