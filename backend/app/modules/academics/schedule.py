"""Lesson generation and conflict checks (ТЗ 4.2)."""

from datetime import date, datetime, time, timedelta

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Group, Lesson, Room, ScheduleRule
from app.models.learning import LessonStatus
from app.services.clock import at_local, local, today

HORIZON_WEEKS = 8


async def conflicts(db: AsyncSession, *, room_id: int, teacher_id: int, starts_at: datetime, ends_at: datetime,
                    exclude_id: int | None = None, exclude_group_id: int | None = None) -> list[str]:
    q = select(Lesson, Group.name).outerjoin(Group, Group.id == Lesson.group_id).where(
        Lesson.status != LessonStatus.CANCELLED,
        Lesson.starts_at < ends_at,
        Lesson.ends_at > starts_at,
        or_(Lesson.room_id == room_id, func.coalesce(Lesson.actual_teacher_id, Lesson.teacher_id) == teacher_id),
    )
    if exclude_id:
        q = q.where(Lesson.id != exclude_id)
    if exclude_group_id:
        q = q.where(or_(Lesson.group_id.is_(None), Lesson.group_id != exclude_group_id))
    out = []
    for lesson, gname in (await db.execute(q)).all():
        who = gname or "индивидуальный урок"
        t = f"{local(lesson.starts_at):%d.%m %H:%M}–{local(lesson.ends_at):%H:%M}"
        if lesson.room_id == room_id:
            room = await db.get(Room, room_id)
            out.append(f"{room.name if room else 'Кабинет'} занят: {who}, {t}")
        else:
            out.append(f"Учитель занят: {who}, {t}")
    return out


async def generate(db: AsyncSession, rule: ScheduleRule, group: Group, until: date | None = None) -> tuple[int, list[str]]:
    """Create planned lessons for the rule up to the horizon. Skips existing ones; reports conflicts."""
    start = max(rule.valid_from, today())
    end = min(rule.valid_to or date.max, until or today() + timedelta(weeks=HORIZON_WEEKS))
    existing = set((await db.scalars(select(Lesson.starts_at).where(Lesson.rule_id == rule.id))).all())
    # The group's own lessons (imported from the old CRM, or made by another rule or by hand) are not a conflict:
    # where the group already has a lesson overlapping the slot, the slot counts as scheduled and is skipped.
    own = (await db.execute(select(Lesson.starts_at, Lesson.ends_at).where(
        Lesson.group_id == group.id, Lesson.status != LessonStatus.CANCELLED, Lesson.ends_at > at_local(start, time(0))))).all()
    created, problems = 0, []
    d = start
    while d <= end:
        if d.weekday() in rule.weekdays:
            s, e = at_local(d, rule.start_time), at_local(d, rule.end_time)
            if s not in existing and not any(a < e and b > s for a, b in own):
                c = await conflicts(db, room_id=rule.room_id, teacher_id=rule.teacher_id, starts_at=s, ends_at=e,
                                    exclude_group_id=group.id)
                if c:
                    problems.append(f"{d:%d.%m}: {c[0]}")
                else:
                    db.add(Lesson(branch_id=group.branch_id, group_id=group.id, level_id=group.level_id,
                                  teacher_id=rule.teacher_id, room_id=rule.room_id, rule_id=rule.id, starts_at=s, ends_at=e))
                    await db.flush()
                    created += 1
        d += timedelta(days=1)
    return created, problems


async def extend_all(db: AsyncSession) -> int:
    """Nightly job: keep every active rule generated HORIZON_WEEKS ahead."""
    total = 0
    rows = (await db.execute(
        select(ScheduleRule, Group).join(Group, Group.id == ScheduleRule.group_id)
        .where(ScheduleRule.archived_at.is_(None), Group.archived_at.is_(None),
               and_(or_(ScheduleRule.valid_to.is_(None), ScheduleRule.valid_to >= today())))
    )).all()
    for rule, group in rows:
        n, _ = await generate(db, rule, group)
        total += n
    return total
