"""Helpers that reverse bonuses when a payment is refunded (ТЗ 10.5)."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Accrual, Payment, Student
from app.services.clock import period_of, today


async def reverse_for_payment(db: AsyncSession, p: Payment, s: Student, actor_id: int) -> int:
    refs = [("payment", p.id)]
    if s.lead_id:
        refs.append(("lead", s.lead_id))
    n = 0
    for ref_type, ref_id in refs:
        for a in await db.scalars(select(Accrual).where(Accrual.ref_type == ref_type, Accrual.ref_id == ref_id,
                                                         Accrual.kind.in_(("sale", "trial_retention", "return")))):
            exists = await db.scalar(select(Accrual.id).where(Accrual.user_id == a.user_id, Accrual.kind == "reversal",
                                                              Accrual.ref_type == f"accrual:{a.kind}", Accrual.ref_id == a.id))
            if exists:
                continue
            db.add(Accrual(user_id=a.user_id, kind="reversal", amount=-a.amount, ref_type=f"accrual:{a.kind}", ref_id=a.id,
                           period=period_of(today()), branch_id=a.branch_id, description=f"Отмена: {a.description} (возврат оплаты)",
                           created_by=actor_id))
            n += 1
    return n
