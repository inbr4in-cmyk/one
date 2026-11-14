"""Paying for a book out of a course payment the student already made («из оплаты»)."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Payment, Student


def lesson_price(s: Student, p: Payment) -> int:
    return s.balance_lesson_price or p.lesson_price or 0


def capacity(s: Student, p: Payment) -> int:
    """How much of payment `p` can still become a book payment: not more than is left of the payment itself and
    not more than is still unspent on the student's balance (money + lessons at their price)."""
    on_balance = max(s.money_balance, 0) + max(s.lessons_left, 0) * lesson_price(s, p)
    return max(0, min(p.amount - p.refunded, on_balance))


async def source(db: AsyncSession, s: Student, amount: int = 1, lock: bool = False) -> Payment | None:
    """The newest course payment entered on the site that still covers `amount`."""
    q = select(Payment).where(Payment.student_id == s.id, Payment.category == "course", Payment.source.is_(None),
                              Payment.amount - Payment.refunded >= amount).order_by(Payment.paid_at.desc(), Payment.id.desc())
    for p in await db.scalars(q.with_for_update() if lock else q):
        if capacity(s, p) >= amount:
            return p
    return None
