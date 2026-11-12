from datetime import timedelta

from app.services.clock import period_of, today
from app.services.payroll import month_days, norm_days
from tests.conftest import branch_id, login, make_staff

YANGI = "Янги шахар"


async def test_timesheet_marks_days_and_pays_salary_by_days(db, client, owner_h):
    bid = await branch_id(db, YANGI)
    admin = await make_staff(db, "branch_admin", [YANGI], "+77030000081", "Админ Филиала")
    clerk = await make_staff(db, "office_manager", [YANGI], "+77030000082", "Офис Окладов")
    teacher = await make_staff(db, "teacher", [YANGI], "+77030000083", "Учитель Тест")
    await db.commit()
    assert (await client.patch(f"/api/staff/{clerk.id}", headers=owner_h, json={"salary": 260000, "pay_scheme": "salary"})).status_code == 200
    ah = await login(client, admin.phone)
    th = await login(client, teacher.phone)
    period = period_of(today())
    past = [d for d in month_days(period) if d <= today() and d.weekday() < 6][:3]
    body = {"user_id": clerk.id, "branch_id": bid, "days": [d.isoformat() for d in past], "status": "work"}
    assert (await client.put("/api/payroll/timesheet", headers=th, json=body)).status_code == 403
    assert (await client.put("/api/payroll/timesheet", headers=ah, json={**body, "days": [(today() + timedelta(days=1)).isoformat()]})).status_code in (400, 422)
    r = await client.put("/api/payroll/timesheet", headers=ah, json=body)
    assert r.status_code == 200, r.text
    ts = (await client.get(f"/api/payroll/timesheet?branch_id={bid}&period={period}", headers=ah)).json()
    row = next(p for p in ts["people"] if p["user_id"] == clerk.id)
    assert row["worked"] == len(past) and row["amount"] == round(260000 * len(past) / norm_days(period))
    assert ts["norm"] == norm_days(period) and ts["can_edit"]
    my = (await client.get(f"/api/payroll?period={period}&branch_id={bid}", headers=ah)).json()
    assert next(p for p in my["people"] if p["user_id"] == clerk.id)["salary_total"] == row["amount"]
    # sick day is not paid; clearing works
    await client.put("/api/payroll/timesheet", headers=ah, json={**body, "days": [past[0].isoformat()], "status": "sick"})
    ts = (await client.get(f"/api/payroll/timesheet?branch_id={bid}&period={period}", headers=ah)).json()
    row = next(p for p in ts["people"] if p["user_id"] == clerk.id)
    assert row["worked"] == len(past) - 1 and row["days"][past[0].isoformat()] == "sick"
    await client.put("/api/payroll/timesheet", headers=ah, json={**body, "days": [past[0].isoformat()], "status": None})
    ts = (await client.get(f"/api/payroll/timesheet?branch_id={bid}&period={period}", headers=ah)).json()
    assert past[0].isoformat() not in next(p for p in ts["people"] if p["user_id"] == clerk.id)["days"]
