"""Lesson balance (ТЗ 5.2–5.3). The ledger is append-only; the student row caches the totals.

Invariant: lessons_paid == lessons_done + lessons_left.
"""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BalanceEntry, Student
from app.services.clock import now


async def apply(
    db: AsyncSession,
    student: Student,
    kind: str,
    *,
    lessons: int = 0,
    money: int = 0,
    price: int | None = None,
    ref: tuple[str, int] | None = None,
    actor_id: int | None = None,
    note: str | None = None,
    counts_as_done: bool = False,
) -> BalanceEntry:
    """lessons > 0 adds lessons; lessons < 0 removes them. counts_as_done: the removal is a held lesson."""
    if counts_as_done:
        student.lessons_done += -lessons
    else:
        student.lessons_paid += lessons
    student.lessons_left += lessons
    student.money_balance += money
    if price is not None and lessons > 0 and kind in ("payment", "transfer", "manual"):
        student.balance_lesson_price = price
    entry = BalanceEntry(
        student_id=student.id, at=now(), kind=kind, lessons_delta=lessons, money_delta=money,
        lesson_price=price if price is not None else student.balance_lesson_price,
        lessons_after=student.lessons_left, money_after=student.money_balance,
        ref_type=ref[0] if ref else None, ref_id=ref[1] if ref else None, actor_id=actor_id, note=note,
    )
    db.add(entry)
    return entry


@dataclass
class TransferCalc:
    same_price: bool
    lessons_before: int
    money_before: int
    old_price: int
    new_price: int
    value: int  # money value of the remaining balance
    lessons_after: int
    money_after: int


def calc_transfer(lessons_left: int, money_balance: int, old_price: int, new_price: int) -> TransferCalc:
    """ТЗ 5.3. Same price → balance moves unchanged. Otherwise value = left × old price (+ money balance),
    new lessons = value // new price, the remainder stays on the money balance.
    Example: 4 × 3000 = 12000 → new price 4000 → 3 lessons, 0 left. 13000 → 3 lessons + 1000."""
    if old_price == new_price or new_price <= 0 or lessons_left <= 0:
        return TransferCalc(True, lessons_left, money_balance, old_price, new_price,
                            max(lessons_left, 0) * old_price + money_balance, lessons_left, money_balance)
    value = lessons_left * old_price + money_balance
    new_lessons = value // new_price
    return TransferCalc(False, lessons_left, money_balance, old_price, new_price, value, new_lessons,
                        value - new_lessons * new_price)
