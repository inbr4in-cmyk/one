"""One-off follow-up, by the owner's written «баланс −4, в долг» of 18.11: students 1462 and 1831 had their wrong
payments removed with the attended lessons forgiven (balance 0). The owner wants the attended lessons to stay a
debt. The balance history is append-only, so one new line takes the forgiven lessons back.

    python 2026-11-18-clear-payments-debt.py            preview, changes nothing
    python 2026-11-18-clear-payments-debt.py commit
"""
import asyncio
import sys

from sqlalchemy import select

from app.core.audit import write_audit
from app.core.db import SessionLocal
from app.models import BalanceEntry, Payment, Student
from app.services import balance as bal

IDS = [1462, 1831]
COMMIT = len(sys.argv) > 1 and sys.argv[1] == "commit"
NOTE = "Посещённые уроки без оплаты не считаются долгом"


async def main():
    async with SessionLocal() as db:
        for sid in IDS:
            s = await db.get(Student, sid, with_for_update=True)
            given = list(await db.scalars(select(BalanceEntry).where(
                BalanceEntry.student_id == sid, BalanceEntry.ref_type == "clear_payments", BalanceEntry.note == NOTE)))
            pays = await db.scalar(select(Payment.id).where(Payment.student_id == sid).limit(1))
            print(f"{s.id} {s.full_name}: paid {s.lessons_paid}, done {s.lessons_done}, left {s.lessons_left}, money {s.money_balance}")
            if len(given) != 1 or pays is not None or s.lessons_left != 0 or s.lessons_paid != given[0].lessons_delta:
                raise SystemExit("the student is not in the expected state (balance 0, no payments, one forgiving line): nothing changed")
            n = given[0].lessons_delta
            print(f"  -> balance {-n} (debt of {n} attended lessons)")
            if not COMMIT:
                continue
            await bal.apply(db, s, "manual", lessons=-n, money=0, ref=("clear_payments_debt", s.id),
                            note="Посещённые уроки без оплаты остаются долгом (по просьбе владельца)")
            await write_audit(db, actor_id=None, action="student.balance_debt", entity="student", entity_id=s.id,
                              branch_id=s.branch_id, ip=None, before={"lessons_left": 0},
                              after={"lessons_left": s.lessons_left},
                              note="По письменной просьбе владельца 18.11: посещённые уроки в долг")
            print(f"  done: paid {s.lessons_paid}, done {s.lessons_done}, left {s.lessons_left}, money {s.money_balance}")
        if COMMIT:
            await db.commit()
        print("committed" if COMMIT else "preview only, nothing changed")


asyncio.run(main())
