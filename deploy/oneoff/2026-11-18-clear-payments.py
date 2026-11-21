"""One-off, by the owner's written request of 18.11: students 1462 and 1831 had their payments and refunds
entered wrongly several times; all of them are removed so staff can enter the right payment again.

Removes the students' payments and the refunds of those payments. The balance history is append-only, so its old
lines stay and one new line takes back what those payments and refunds gave; the attended lessons stay.

    python 2026-11-18-clear-payments.py            preview, changes nothing
    python 2026-11-18-clear-payments.py debt       remove; attended lessons become a debt (balance = -attended)
    python 2026-11-18-clear-payments.py zero       remove; attended lessons are not a debt (balance = 0)
"""
import asyncio
import sys

from sqlalchemy import delete, select

from app.core.audit import write_audit
from app.core.db import SessionLocal
from app.models import BalanceEntry, Payment, Refund, Student
from app.services import balance as bal

IDS = [1462, 1831]
MODE = sys.argv[1] if len(sys.argv) > 1 else "preview"
assert MODE in ("preview", "debt", "zero")


async def main():
    async with SessionLocal() as db:
        for sid in IDS:
            s = await db.get(Student, sid, with_for_update=True)
            pays = list(await db.scalars(select(Payment).where(Payment.student_id == sid).order_by(Payment.id)))
            pids = [p.id for p in pays]
            refs = list(await db.scalars(select(Refund).where(Refund.payment_id.in_(pids)).order_by(Refund.id))) if pids else []
            entries = list(await db.scalars(select(BalanceEntry).where(BalanceEntry.student_id == sid).order_by(BalanceEntry.at, BalanceEntry.id)))
            keep = [e for e in entries if e.kind == "lesson"]
            drop = [e for e in entries if e.kind != "lesson"]
            done = -sum(e.lessons_delta for e in keep)
            print(f"\n{s.id} {s.full_name}: paid {s.lessons_paid}, done {s.lessons_done}, left {s.lessons_left}, money {s.money_balance}")
            for p in pays:
                print(f"  payment #{p.id} {p.category} {p.amount} / {p.lessons} lessons, refunded {p.refunded}, source {p.source}")
            for r in refs:
                print(f"  refund #{r.id} of payment #{r.payment_id}: {r.amount} / {r.lessons_removed} lessons")
            for e in drop:
                print(f"  undo   entry {e.id} {e.kind} lessons {e.lessons_delta:+} money {e.money_delta:+} {e.ref_type}:{e.ref_id} {e.note or ''}")
            for e in keep:
                print(f"  keep   entry {e.id} {e.kind} lessons {e.lessons_delta:+} {e.note or ''}")
            if any(p.category != "course" or p.source for p in pays):
                raise SystemExit("unexpected payment kind (book/shop/import): stop, nothing changed")
            if done < 0:
                raise SystemExit("unexpected lesson history: stop, nothing changed")
            after = -done if MODE == "debt" else 0
            print(f"  -> payments 0, refunds 0, attended lessons {done}, balance after: {after if MODE != 'preview' else f'-{done} (debt) or 0 (zero)'}")
            if MODE == "preview":
                continue
            before = {"lessons_paid": s.lessons_paid, "lessons_left": s.lessons_left, "money_balance": s.money_balance,
                      "payments": [{"id": p.id, "amount": p.amount, "lessons": p.lessons, "refunded": p.refunded} for p in pays],
                      "refunds": [{"id": r.id, "amount": r.amount, "lessons": r.lessons_removed} for r in refs]}
            if refs:
                await db.execute(delete(Refund).where(Refund.id.in_([r.id for r in refs])))
            if pids:
                await db.execute(delete(Payment).where(Payment.id.in_(pids)))
            # The balance history is append-only: the old lines stay, one new line takes back everything the
            # removed payments and refunds had given, so only the attended lessons are left.
            lessons = sum(e.lessons_delta for e in drop)
            money = sum(e.money_delta for e in drop)
            if lessons or money:
                await bal.apply(db, s, "manual", lessons=-lessons, money=-money, ref=("clear_payments", s.id),
                                note="Оплаты и возвраты удалены как ошибочные (по просьбе владельца)")
            if (s.lessons_paid, s.lessons_left, s.money_balance) != (0, -done, 0):
                raise SystemExit(f"balance does not add up for {s.id}: {s.lessons_paid}/{s.lessons_left}/{s.money_balance}; nothing changed")
            if MODE == "zero" and done:
                await bal.apply(db, s, "manual", lessons=done, money=0, price=s.balance_lesson_price, ref=("clear_payments", s.id),
                                note="Посещённые уроки без оплаты не считаются долгом")
            await write_audit(db, actor_id=None, action="student.payments_cleared", entity="student", entity_id=s.id,
                              branch_id=s.branch_id, ip=None, before=before,
                              after={"lessons_paid": s.lessons_paid, "lessons_left": s.lessons_left, "money_balance": s.money_balance},
                              note="По письменной просьбе владельца 18.11: ошибочные оплаты и возвраты удалены")
            print(f"  done: paid {s.lessons_paid}, done {s.lessons_done}, left {s.lessons_left}, money {s.money_balance}")
        if MODE != "preview":
            await db.commit()
        print("\ncommitted" if MODE != "preview" else "\npreview only, nothing changed")


asyncio.run(main())
