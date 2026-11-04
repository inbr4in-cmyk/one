"""Helpers that reverse bonuses when a payment is refunded (ТЗ 10.5, QA B-3)."""

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Accrual, Payment, Student
from app.services.clock import period_of, today

SALE_KINDS = ("sale", "trial_retention", "return")


async def _already_reversed(db: AsyncSession, a: Accrual) -> int:
    """Sum (positive) of reversals already booked for this accrual: the old one-shot row and per-refund rows."""
    total = await db.scalar(select(func.coalesce(func.sum(Accrual.amount), 0)).where(
        Accrual.user_id == a.user_id, Accrual.kind == "reversal", Accrual.ref_id == a.id,
        or_(Accrual.ref_type == f"accrual:{a.kind}", Accrual.ref_type.like(f"refund:%:{a.kind}"))))
    return -int(total or 0)


async def reverse_for_payment(db: AsyncSession, p: Payment, s: Student, actor_id: int, *,
                              share: tuple[int, int] = (1, 1), refund_id: int | None = None) -> int:
    """share = (refunded so far, total): 1/1 reverses everything; 3/8 reverses 3/8 of each bonus overall.
    Repeated partial refunds top the reversal up to the new share, never past the bonus itself."""
    refs = [("payment", p.id)]
    if s.lead_id:
        refs.append(("lead", s.lead_id))
    done, total = share
    full = done >= total
    n = 0
    for ref_type, ref_id in refs:
        for a in await db.scalars(select(Accrual).where(Accrual.ref_type == ref_type, Accrual.ref_id == ref_id,
                                                         Accrual.kind.in_(SALE_KINDS))):
            target = a.amount if full else a.amount * done // total
            delta = target - await _already_reversed(db, a)
            if delta <= 0:
                continue
            what = "возврат оплаты" if full else f"частичный возврат {done}/{total}"
            db.add(Accrual(user_id=a.user_id, kind="reversal", amount=-delta,
                           ref_type=f"refund:{refund_id}:{a.kind}" if refund_id else f"accrual:{a.kind}", ref_id=a.id,
                           period=period_of(today()), branch_id=a.branch_id, description=f"Отмена: {a.description} ({what})"[:255],
                           created_by=actor_id))
            await db.flush()
            n += 1
    return n
