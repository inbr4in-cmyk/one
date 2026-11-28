"""Two lessons of one group on one day where only one was really held (a past lesson created over a held one).

`find` only reads; `fix` cancels the extra lesson, gives its charged lessons back to the students and takes its pay
off the teacher. A lesson moved by hand or added by hand is a real second lesson and is never touched."""

from collections import defaultdict
from datetime import date, time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Accrual, Attendance, Group, Lesson, ScheduleRule, Student
from app.models.learning import AttendanceStatus, LessonStatus
from app.services import absences
from app.services import balance as bal
from app.services.clock import at_local, local, period_of, today
from app.services.payroll import period_locked

REASON = "Дубликат урока"


def _made_later(x: Lesson) -> bool:
    """Made from the schedule after the lesson time had already passed («Прошедшие уроки», a rule entered late)."""
    return x.rule_id is not None and x.moved_from_id is None and x.created_at > x.ends_at


async def find(db: AsyncSession, since: date, keep: str = "old") -> list[dict]:
    """Days with an extra lesson. keep='old': the lesson that existed first stays; keep='new': the lesson of the
    schedule that is in force now stays."""
    rows = list(await db.scalars(select(Lesson).where(
        Lesson.group_id.is_not(None), Lesson.is_support.is_(False), Lesson.starts_at >= at_local(since, time(0)),
        Lesson.starts_at < at_local(today(), time(0))).order_by(Lesson.starts_at, Lesson.id)))
    moved_from = {x.moved_from_id for x in rows if x.moved_from_id}
    rules = {r.id: r for r in await db.scalars(select(ScheduleRule))}
    days: dict[tuple[int, date], list[Lesson]] = defaultdict(list)
    for x in rows:
        days[(x.group_id, local(x.starts_at).date())].append(x)
    out = []
    for (gid, day), items in sorted(days.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        live = [x for x in items if x.status != LessonStatus.CANCELLED]
        moved_away = any(x.status == LessonStatus.CANCELLED and x.id in moved_from for x in items)
        by_hand = [x for x in live if x.rule_id is None or x.moved_from_id is not None]
        ruled = [x for x in live if x not in by_hand]
        extra: list[Lesson] = []
        keeper: Lesson | None = None
        if by_hand:
            # a moved or hand-made lesson is deliberate; a schedule lesson that was already there is a real second
            # lesson, one created afterwards over it is the duplicate
            extra, keeper = [x for x in ruled if _made_later(x)], by_hand[0]
        elif len(ruled) > 1:
            def in_force(x: Lesson) -> bool:
                r = rules.get(x.rule_id)
                return r is not None and r.archived_at is None and (r.valid_to is None or r.valid_to > day)

            order = sorted(ruled, key=lambda x: ((not in_force(x), _made_later(x)) if keep == "new" else (_made_later(x), not in_force(x)), x.id))
            keeper, extra = order[0], order[1:]
        elif moved_away and ruled and _made_later(ruled[0]):
            extra = ruled  # the lesson of this day was moved to another day; a new one was created in its place
        if not extra:
            continue
        g = await db.get(Group, gid)
        for x in extra:
            marks = list(await db.scalars(select(Attendance).where(Attendance.lesson_id == x.id)))
            acc = await db.scalar(select(Accrual).where(Accrual.kind == "lesson", Accrual.ref_type == "lesson", Accrual.ref_id == x.id))
            out.append({"lesson_id": x.id, "keep_id": keeper.id if keeper else None, "group_id": gid, "group": g.name if g else "",
                        "date": day.isoformat(), "time": f"{local(x.starts_at):%H:%M}",
                        "keep_time": f"{local(keeper.starts_at):%H:%M}" if keeper else None,
                        "marks": len(marks), "charged": sum(1 for a in marks if a.charged),
                        "teacher_id": acc.user_id if acc else None, "pay": acc.amount if acc else 0})
    return out


async def fix(db: AsyncSession, since: date, keep: str, actor_id: int | None) -> dict:
    items = await find(db, since, keep)
    back = pay = 0
    for it in items:
        x = await db.get(Lesson, it["lesson_id"])
        when = local(x.starts_at)
        excused: set[int] = set()
        for a in await db.scalars(select(Attendance).where(Attendance.lesson_id == x.id)):
            if a.student_id is None:
                continue
            s = await db.get(Student, a.student_id)
            if a.status == AttendanceStatus.EXCUSED:
                excused.add(s.id)
            if a.charged:
                await bal.apply(db, s, "lesson", lessons=1, price=s.balance_lesson_price, ref=("attendance", x.id),
                                actor_id=actor_id, counts_as_done=True, note=f"Возврат урока {when:%d.%m %H:%M}: дубликат урока")
                a.charged = False
                back += 1
        x.status, x.cancel_reason = LessonStatus.CANCELLED, REASON
        await db.flush()
        for sid in excused:  # the free excused absence of the month may now fall on another lesson
            await absences.rebalance_excused(db, await db.get(Student, sid), when.date(), actor_id)
        acc = await db.scalar(select(Accrual).where(Accrual.kind == "lesson", Accrual.ref_type == "lesson", Accrual.ref_id == x.id))
        if acc is not None and acc.amount:
            pay += acc.amount
            if await period_locked(db, acc.period, acc.branch_id):
                db.add(Accrual(user_id=acc.user_id, kind="correction", amount=-acc.amount, ref_type=f"lesson:{x.id}", ref_id=None,
                               period=period_of(today()), branch_id=acc.branch_id,
                               description=f"Исправление: {acc.description} (дубликат урока)", created_by=actor_id))
            else:
                acc.amount, acc.description = 0, f"{acc.description} · дубликат урока, отменён"
    await db.commit()
    return {"lessons": len(items), "returned_to_students": back, "teacher_pay_removed": pay, "items": items}
