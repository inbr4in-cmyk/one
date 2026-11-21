"""Accruals from facts (ТЗ 10). Every bonus is unique per (user, kind, fact) — see Accrual's constraint."""

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Accrual, Lesson, PayrollPeriod, Room
from app.services.clock import period_of
from app.services.values import rate


async def period_locked(db: AsyncSession, period: str, branch_id: int | None) -> bool:
    if branch_id is None:
        return False
    p = await db.scalar(select(PayrollPeriod).where(PayrollPeriod.period == period, PayrollPeriod.branch_id == branch_id))
    return p is not None and p.status != "draft"


async def on_rates(db: AsyncSession, user_id: int) -> bool:
    """Staff on «оклад only» get no per-fact accruals (lessons, sales, trials…)."""
    from app.models import User
    return (await db.scalar(select(User.pay_scheme).where(User.id == user_id))) != "salary"


TIMESHEET_FROM = "2026-11"
WORK_WEEKDAYS = (0, 1, 2, 3, 4, 5)  # Mon–Sat; Sunday is a day off


def month_days(period: str) -> list[date]:
    from datetime import timedelta
    y, m = (int(x) for x in period.split("-"))
    d, out = date(y, m, 1), []
    while d.month == m:
        out.append(d)
        d += timedelta(days=1)
    return out


def norm_days(period: str) -> int:
    """Working days in the month (Mon–Sat): the salary is divided by this."""
    return sum(1 for d in month_days(period) if d.weekday() in WORK_WEEKDAYS)


async def worked_days(db: AsyncSession, user_id: int, period: str) -> tuple[int, int]:
    from app.models import StaffDay
    days = month_days(period)
    n = await db.scalar(select(func.count()).select_from(StaffDay).where(
        StaffDay.user_id == user_id, StaffDay.status == "work", StaffDay.day >= days[0], StaffDay.day <= days[-1]))
    return int(n or 0), norm_days(period)


async def accrue_salary(db: AsyncSession, user, period: str) -> int:
    """The month's fixed salary as one accrual per person and month. The amount follows the staff card while the
    month's sheet is not approved; nothing is added for an inactive person or without a salary."""
    from app.models import UserBranch
    ref_id = int(period.replace("-", ""))
    existing = await db.scalar(select(Accrual).where(Accrual.user_id == user.id, Accrual.kind == "salary",
                                                     Accrual.ref_type == "salary", Accrual.ref_id == ref_id))
    if existing is None and not (user.salary and user.pay_scheme in ("salary", "both")):
        return 0
    want = user.salary if user.pay_scheme in ("salary", "both") and user.is_active and user.archived_at is None else 0
    days_note = ""
    if want and period >= TIMESHEET_FROM:
        # From November 2026 the salary is paid for the days marked «work» in the timesheet (табель).
        worked, norm = await worked_days(db, user.id, period)
        want = round(want * worked / norm) if norm else 0
        days_note = f": {worked} из {norm} дн."
    y, m = period.split("-")
    desc = f"Оклад за {m}.{y}{days_note}"
    if existing is not None:
        if (existing.amount != want or existing.description != desc) and not await period_locked(db, existing.period, existing.branch_id):
            existing.amount, existing.description = want, desc
            return 1
        return 0
    if not want:
        return 0
    branch_id = await db.scalar(select(func.min(UserBranch.branch_id)).where(UserBranch.user_id == user.id))
    db.add(Accrual(user_id=user.id, kind="salary", amount=want, ref_type="salary", ref_id=ref_id, period=period,
                   branch_id=branch_id, description=desc))
    return 1


async def accrue_salaries(db: AsyncSession, period: str | None = None) -> int:
    from app.models import User
    from app.models.identity import UserKind
    from app.services.clock import today
    period = period or period_of(today())
    n = 0
    for u in await db.scalars(select(User).where(User.kind == UserKind.STAFF)):
        n += await accrue_salary(db, u, period)
    return n


async def accrue_once(
    db: AsyncSession, *, user_id: int, kind: str, amount: int, ref: tuple[str, int], on: date,
    branch_id: int | None, description: str, created_by: int | None = None,
) -> bool:
    """Insert the accrual unless this fact already produced it. Returns True if a new accrual was created."""
    if not await on_rates(db, user_id):
        return False
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
                        group_name: str, actor_id: int | None, kind: str = "group") -> None:
    """Upsert the pay for one held lesson. If the attendance is corrected later the amount follows; once the
    period is approved, the difference goes into the next open period as a correction."""
    room_rate = await db.scalar(select(Room.teacher_rate).join(Lesson, Lesson.room_id == Room.id).where(Lesson.id == lesson_id))
    if kind == "support":
        # Support: paid by the length of the lesson, the rate is for 30 minutes (1000 → an hour is 2000).
        les = await db.get(Lesson, lesson_id)
        minutes = max(0, round((les.ends_at - les.starts_at).total_seconds() / 60))
        amount = round(await rate(db, "teacher_support_lesson", on) * minutes / 30)
    elif kind == "club":
        amount = await rate(db, "teacher_club_lesson", on)
    elif room_rate:
        # A room with its own pay: the same fixed sum for a group, duo or individual lesson, no per-student extra.
        amount = room_rate
    elif kind in ("individual", "duo"):
        # Individual and duo lessons: a flat rate per held lesson, no per-student extra.
        amount = await rate(db, f"teacher_{kind}_lesson", on)
    else:
        base = await rate(db, "teacher_lesson_base", on)
        extra = await rate(db, "teacher_extra_per_student", on)
        threshold = await rate(db, "teacher_extra_threshold", on)
        amount = teacher_lesson_pay(n, base, extra, threshold)
    nobody = noshow = False
    if kind in ("individual", "duo"):
        # An individual (or duo) lesson nobody came to — the student asked off or did not show up — is not paid,
        # in a room with its own rate too. A trial visitor counts as someone who came.
        from app.models import Attendance
        from app.models.learning import AttendanceStatus
        came = await db.scalar(select(func.count()).select_from(Attendance).where(
            Attendance.lesson_id == lesson_id, Attendance.status.in_((AttendanceStatus.PRESENT, AttendanceStatus.LATE))))
        if not came:
            amount, nobody = 0, True
            # Owner's rule from 01.11.2026: an individual lesson the student missed and lost from the balance
            # (no warning, or asked off again that month) still pays the teacher a small fixed sum.
            if kind == "individual" and on >= date(2026, 11, 1) and await db.scalar(select(Attendance.id).where(
                    Attendance.lesson_id == lesson_id, Attendance.charged.is_(True)).limit(1)):
                amount, noshow = await rate(db, "teacher_individual_noshow", on), True
    if not await on_rates(db, teacher_id):
        amount = 0  # оклад only: the lesson is recorded, the pay is in the salary
    desc = f"Урок {group_name} {on.strftime('%d.%m')}: " + ("ученик не пришёл, урок списан" if noshow else "ученик не пришёл, без оплаты" if nobody else f"{n} уч.")
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
