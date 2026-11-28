"""Owner, 23.11.2026: Админ филиала / Офис-менеджер are not paid for a trial visit. Removes the November
trial_visit accruals of such staff (not of anyone who also holds Отдел продаж). Preview by default; `commit` applies
only when the totals equal the numbers the owner approved (14 accruals, 28 000)."""
import asyncio
import sys

from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import Accrual, PayrollPeriod, Role, User, UserRole

PERIOD, WANT_N, WANT_SUM = "2026-11", 14, 28000
COMMIT = len(sys.argv) > 1 and sys.argv[1] == "commit"


async def main():
    async with SessionLocal() as db:
        rows = list(await db.scalars(select(Accrual).where(Accrual.kind == "trial_visit", Accrual.period == PERIOD).order_by(Accrual.id)))
        hit = []
        for a in rows:
            codes = set(await db.scalars(select(Role.code).join(UserRole, UserRole.role_id == Role.id).where(UserRole.user_id == a.user_id)))
            if codes & {"branch_admin", "office_manager"} and "sales" not in codes:
                hit.append(a)
                u = await db.get(User, a.user_id)
                print(a.id, u.full_name, sorted(codes), a.amount, a.description)
        total = sum(a.amount for a in hit)
        closed = list(await db.scalars(select(PayrollPeriod).where(PayrollPeriod.period == PERIOD, PayrollPeriod.status != "draft")))
        print("accruals:", len(hit), "sum:", total, "closed payroll periods:", [(p.branch_id, p.status) for p in closed])
        if not COMMIT:
            print("preview only")
            return
        if len(hit) != WANT_N or total != WANT_SUM or closed:
            print("STOP: numbers differ from the approved 14 / 28000 or the period is closed; nothing changed")
            return
        for a in hit:
            await db.delete(a)
        await db.commit()
        print("removed", len(hit), total)


asyncio.run(main())
