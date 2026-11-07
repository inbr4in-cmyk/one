"""Accruals from facts (ТЗ 10). Every bonus is unique per (user, kind, fact) — see Accrual's constraint."""

from datetime import date

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Accrual, PayrollPeriod
from app.services.clock import period_of
from app.services.values import rate


async def period_locked(db: AsyncSession, period: str, branch_id: int | None) -> bool:
    if branch_id is None:
        return False
    p = await db.scalar(select(PayrollPeriod).where(PayrollPeriod.period == period, PayrollPeriod.branch_id == branch_id))
    return p is not None and p.status != "draft"


async def accrue_once(
    db: AsyncSession, *, user_id: int, kind: str, amount: int, ref: tuple[str, int], on: date,
    branch_id: int | None, description: str, created_by: int | None = None,
) -> bool:
    """Insert the accrual unless this fact already produced it. Returns True if a new accrual was created."""
    stmt = (
        insert(Accrual)
        .values(user_id=user_id, kind=kind, amount=amount, ref_type=ref[0], ref_id=ref[1], period=period_of(on),
                branch_id=branch_id, description=description, created_by=created_by)
        .on_conflict_do_nothing(constraint="accruals_user_id_kind_ref_type_ref_id_key")
        .returning(Accrual.id)
    )
    return (await db.execute(stmt)).scalar() is not None


def teacher_lesson_pay(n: int, base: int, extra: int, threshold: int) -> int:
    """ТЗ 10.2: 2500 + 100 × (N − 5), and just 2500 when N ≤ 5."""
    return base + extra * max(0, n - threshold)


async def accrue_lesson(db: AsyncSession, *, teacher_id: int, lesson_id: int, n: int, on: date, branch_id: int,
                        group_name: str, actor_id: int | None) -> None:
    """Upsert the pay for one held lesson. If the attendance is corrected later the amount follows; once the
    period is approved, the difference goes into the next open period as a correction."""
    base = await rate(db, "teacher_lesson_base", on)
    extra = await rate(db, "teacher_extra_per_student", on)
    threshold = await rate(db, "teacher_extra_threshold", on)
    amount = teacher_lesson_pay(n, base, extra, threshold)
    desc = f"Урок {group_name} {on.strftime('%d.%m')}: {n} уч."
    existing = await db.scalar(select(Accrual).where(Accrual.kind == "lesson", Accrual.ref_type == "lesson",
                                                     Accrual.ref_id == lesson_id))
    if existing is None:
        await accrue_once(db, user_id=teacher_id, kind="lesson", amount=amount, ref=("lesson", lesson_id), on=on,
                          branch_id=branch_id, description=desc, created_by=actor_id)
        return
    if existing.amount == amount and existing.user_id == teacher_id:
        return
    if not await period_locked(db, existing.period, existing.branch_id):
        existing.amount, existing.user_id, existing.description = amount, teacher_id, desc
        return
    # Approved period: compensate in the current period.
    from app.services.clock import today

    db.add(Accrual(user_id=existing.user_id, kind="correction", amount=-existing.amount, ref_type=f"lesson:{lesson_id}",
                   ref_id=None, period=period_of(today()), branch_id=branch_id,
                   description=f"Исправление: {existing.description}", created_by=actor_id))
    db.add(Accrual(user_id=teacher_id, kind="correction", amount=amount, ref_type=f"lesson:{lesson_id}", ref_id=None,
                   period=period_of(today()), branch_id=branch_id, description=f"Исправление: {desc}", created_by=actor_id))
    existing.description = f"{existing.description} (исправлено)"
