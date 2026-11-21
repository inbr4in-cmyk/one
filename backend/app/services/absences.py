"""Owner's rule of 21.11.2026, in force for lessons from 01.11.2026: a student may ask off («отпросился») once a
calendar month without losing the lesson; every further excused absence that month is taken from the balance like
an absence without a reason. Counted per student over all his groups, by the date of the lesson."""

from datetime import date, time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Attendance, Freeze, Lesson, Student
from app.models.learning import AttendanceStatus, LessonStatus
from app.services import balance as bal
from app.services.clock import at_local, local
from sqlalchemy import func

RULE_FROM = date(2026, 11, 1)
FREE_PER_MONTH = 1


def month_of(d: date) -> tuple[date, date]:
    start = d.replace(day=1)
    return start, (start.replace(year=start.year + 1, month=1) if start.month == 12 else start.replace(month=start.month + 1))


async def rebalance_excused(db: AsyncSession, s: Student, day: date, actor_id: int | None) -> list[int]:
    """Put the month's excused absences of the student in order: the first one is free, the rest are charged.
    Returns the lessons whose charge changed (their teacher pay may depend on it)."""
    start, end = month_of(day)
    if start < RULE_FROM:
        return []
    await db.flush()
    rows = (await db.execute(
        select(Attendance, Lesson).join(Lesson, Lesson.id == Attendance.lesson_id)
        .where(Attendance.student_id == s.id, Attendance.status == AttendanceStatus.EXCUSED,
               Lesson.status != LessonStatus.CANCELLED, Lesson.is_support.is_(False),
               Lesson.starts_at >= at_local(start, time(0)), Lesson.starts_at < at_local(end, time(0)))
        .order_by(Lesson.starts_at, Lesson.id))).all()
    free, changed = FREE_PER_MONTH, []
    for a, lesson in rows:
        on = local(lesson.starts_at)
        frozen = await db.scalar(select(Freeze.id).where(
            Freeze.student_id == s.id, Freeze.starts_on <= on.date(),
            func.coalesce(Freeze.ended_early_on, Freeze.ends_on) > on.date()).limit(1)) is not None
        if frozen:
            want = False  # a frozen day is never charged and does not use up the free absence
        elif free > 0:
            want, free = False, free - 1
        else:
            want = True
        if want != a.charged:
            await bal.apply(db, s, "lesson", lessons=-1 if want else 1, price=s.balance_lesson_price,
                            ref=("attendance", lesson.id), actor_id=actor_id, counts_as_done=True,
                            note=(f"Урок {on:%d.%m %H:%M}: отпросился повторно за месяц" if want
                                  else f"Возврат урока {on:%d.%m %H:%M}: первый пропуск по причине за месяц"))
            a.charged = want
            changed.append(lesson.id)
    return changed
