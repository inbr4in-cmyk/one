"""One-off, by the owner's written request of 21.11: the new absence rules count from 01.11.2026.

  1. «Отпросился»: the first excused absence of a student in a calendar month is free, every next one that month is
     taken from the balance (group, duo, individual).
  2. Individual lesson the student missed and lost from the balance: the teacher gets the no-show rate
     (teacher_individual_noshow, 1000) instead of 0.

Lessons the students attended and absences without a reason are not touched. Preview does the whole recount inside
a transaction, prints every change and rolls it back.

    python 2026-11-21-absence-rules.py            preview, changes nothing
    python 2026-11-21-absence-rules.py commit     apply
"""
import asyncio
import sys
from datetime import time

from sqlalchemy import func, select

from app.core.audit import write_audit
from app.core.db import SessionLocal
from app.models import Accrual, Attendance, Group, Lesson, Student, User
from app.models.learning import AttendanceStatus, LessonStatus
from app.modules.academics.router import accrue_for_lesson
from app.services import absences
from app.services.clock import at_local, local, today

COMMIT = len(sys.argv) > 1 and sys.argv[1] == "commit"


async def totals(db):
    return (int(await db.scalar(select(func.coalesce(func.sum(Student.lessons_left), 0)))),
            int(await db.scalar(select(func.coalesce(func.sum(Accrual.amount), 0)))))


async def main():
    async with SessionLocal() as db:
        start = at_local(absences.RULE_FROM, time(0))
        before = await totals(db)
        # 1. excused absences, month by month
        months, d = [], absences.RULE_FROM
        while d <= today():
            months.append(d)
            d = absences.month_of(d)[1]
        charged = 0
        for m in months:
            a, b = absences.month_of(m)
            sids = (await db.scalars(
                select(Attendance.student_id).join(Lesson, Lesson.id == Attendance.lesson_id)
                .where(Attendance.student_id.is_not(None), Attendance.status == AttendanceStatus.EXCUSED,
                       Lesson.status != LessonStatus.CANCELLED, Lesson.is_support.is_(False),
                       Lesson.starts_at >= at_local(a, time(0)), Lesson.starts_at < at_local(b, time(0)))
                .group_by(Attendance.student_id).order_by(Attendance.student_id))).all()
            print(f"\n{m:%m.%Y}: students who asked off: {len(sids)}")
            for sid in sids:
                s = await db.get(Student, sid, with_for_update=True)
                left = s.lessons_left
                changed = await absences.rebalance_excused(db, s, m, None)
                if changed:
                    days = [f"{local((await db.get(Lesson, lid)).starts_at):%d.%m}" for lid in changed]
                    charged += left - s.lessons_left
                    print(f"  {s.id} {s.full_name}: lessons {left} -> {s.lessons_left} (lessons of {', '.join(days)})")
                    if COMMIT:
                        await write_audit(db, actor_id=None, action="student.absence_rules", entity="student", entity_id=s.id,
                                          branch_id=s.branch_id, ip=None, before={"lessons_left": left},
                                          after={"lessons_left": s.lessons_left, "lessons": changed},
                                          note="Правило с 01.11: один пропуск по причине в месяц без списания")
        print(f"\nlessons taken for repeated excused absences: {charged}")
        # 2. teacher pay for individual lessons nobody came to
        await db.flush()
        rows = (await db.execute(
            select(Lesson, Group.name).outerjoin(Group, Group.id == Lesson.group_id)
            .where(Lesson.attendance_marked_at.is_not(None), Lesson.status != LessonStatus.CANCELLED, Lesson.starts_at >= start,
                   Lesson.is_support.is_(False), (Lesson.group_id.is_(None)) | (Group.kind == "individual"))
            .order_by(Lesson.starts_at))).all()
        added = 0
        print(f"\nindividual lessons held since {absences.RULE_FROM:%d.%m}: {len(rows)}")
        for lesson, gname in rows:
            came = await db.scalar(select(func.count()).select_from(Attendance).where(
                Attendance.lesson_id == lesson.id, Attendance.status.in_((AttendanceStatus.PRESENT, AttendanceStatus.LATE))))
            if came:
                continue
            acc = await db.scalar(select(Accrual).where(Accrual.kind == "lesson", Accrual.ref_type == "lesson", Accrual.ref_id == lesson.id))
            old = acc.amount if acc else None
            await accrue_for_lesson(db, lesson, None)
            await db.flush()
            if acc is not None:
                await db.refresh(acc)
            else:
                acc = await db.scalar(select(Accrual).where(Accrual.kind == "lesson", Accrual.ref_type == "lesson", Accrual.ref_id == lesson.id))
            new = acc.amount if acc else None
            corr = int(await db.scalar(select(func.coalesce(func.sum(Accrual.amount), 0)).where(
                Accrual.kind == "correction", Accrual.ref_type == f"lesson:{lesson.id}")) or 0)
            if new != old or corr:
                t = await db.get(User, lesson.actual_teacher_id or lesson.teacher_id)
                added += (new or 0) - (old or 0)
                print(f"  {local(lesson.starts_at):%d.%m %H:%M} {gname or 'индивидуально'} · {t.full_name if t else '?'}: {old} -> {new}"
                      + (f" (closed month: correction lines {corr:+})" if corr else ""))
        after = await totals(db)
        print(f"\nteacher pay added for missed individual lessons: {added}")
        print(f"sum of lessons left: {before[0]} -> {after[0]}; sum of accruals: {before[1]} -> {after[1]}")
        if COMMIT:
            await db.commit()
            print("\ncommitted")
        else:
            await db.rollback()
            print("\npreview only, nothing changed")


asyncio.run(main())
