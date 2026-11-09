from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, or_, select, true
from sqlalchemy.exc import IntegrityError

from app.core.audit import snapshot, write_audit
from app.core.deps import DB, Actor, require_staff, require
from app.core.errors import bad_request, conflict, forbidden, not_found
from app.core.permissions import NETWORK, OWN
from app.core.schemas import In, ORM
from app.models import (
    Attendance,
    Group,
    GroupMember,
    Homework,
    HomeworkSubmission,
    Lead,
    Level,
    UserBranch,
    Lesson,
    Room,
    ScheduleRule,
    Student,
    User,
)
from app.models.identity import UserKind
from app.models.learning import AttendanceStatus, LessonStatus, StudentStatus
from app.modules.academics import schedule as sched
from app.modules.students.router import is_frozen_on
from app.modules.students.scope import get_student_scoped
from app.services import balance as bal
from app.services import chats, crm
from app.services.clock import end_of_local_day, local, now, today
from app.services.coins import award_auto
from app.services.messaging import notify_guardians
from app.services.payroll import accrue_lesson
from app.services.values import setting

router = APIRouter(tags=["academics"])


# ---------- groups ----------
class GroupIn(In):
    name: str = Field(min_length=1, max_length=120)
    branch_id: int
    level_id: int
    teacher_id: int
    room_id: int | None = None
    capacity: int = Field(default=12, ge=1, le=100)
    starts_on: date | None = None
    status: str = Field(default="active", pattern="^(recruiting|active|finished)$")
    # group | duo (2 students) | individual (1 student)
    kind: str = Field(default="group", pattern="^(group|duo|individual)$")


KIND_CAPACITY = {"individual": 1, "duo": 2}


class GroupOut(ORM):
    id: int
    name: str
    branch_id: int
    level_id: int
    teacher_id: int
    room_id: int | None
    capacity: int
    starts_on: date | None
    status: str
    kind: str = "group"
    chat_id: int | None
    members: int = 0
    teacher_name: str | None = None
    schedule: list[dict] = []


def group_filter(actor: Actor, action: str = "view"):
    scope = actor.scope("students", action) if actor.can("students", action) else actor.scope("schedule", "view")
    if scope == NETWORK:
        return true()
    if scope == OWN:
        return Group.teacher_id == actor.id
    return Group.branch_id.in_(actor.branch_ids or {-1})


async def _group_out(db: DB, g: Group) -> GroupOut:
    o = GroupOut.model_validate(g)
    o.members = await db.scalar(select(func.count()).select_from(GroupMember).where(GroupMember.group_id == g.id,
                                                                                      GroupMember.left_on.is_(None)))
    t = await db.get(User, g.teacher_id)
    o.teacher_name = t.full_name if t else None
    o.schedule = [{"id": r.id, "weekdays": r.weekdays, "start": r.start_time.strftime("%H:%M"), "end": r.end_time.strftime("%H:%M"),
                   "room_id": r.room_id} for r in await db.scalars(select(ScheduleRule).where(
                       ScheduleRule.group_id == g.id, ScheduleRule.archived_at.is_(None)))]
    return o


async def _get_group(db: DB, actor: Actor, group_id: int, action: str = "view") -> Group:
    g = await db.scalar(select(Group).where(Group.id == group_id, group_filter(actor, action)))
    if g is None:
        raise not_found("Группа")
    return g


async def _check_teacher(db: DB, teacher_id: int, branch_id: int) -> User:
    t = await db.get(User, teacher_id)
    if t is None or t.kind != UserKind.STAFF or not t.is_active or t.archived_at is not None:
        raise bad_request("Учитель не найден")
    if not await db.scalar(select(UserBranch.id).where(UserBranch.user_id == t.id, UserBranch.branch_id == branch_id)):
        raise bad_request("Учитель не работает в этом филиале")
    return t


@router.get("/groups", response_model=list[GroupOut])
async def list_groups(db: DB, actor: Actor = require("schedule", "view"), branch_id: int | None = None,
                      level_id: int | None = None, teacher_id: int | None = None, archived: bool = False,
                      kind: str | None = Query(default=None, pattern="^(group|duo|individual)$")) -> list[GroupOut]:
    q = select(Group).where(group_filter(actor))
    if kind:
        q = q.where(Group.kind == kind)
    q = q.where(Group.archived_at.is_not(None) if archived else Group.archived_at.is_(None))
    if branch_id:
        q = q.where(Group.branch_id == branch_id)
    if level_id:
        q = q.where(Group.level_id == level_id)
    if teacher_id:
        q = q.where(Group.teacher_id == teacher_id)
    return [await _group_out(db, g) for g in await db.scalars(q.order_by(Group.name))]


@router.post("/groups", response_model=GroupOut, status_code=201)
async def create_group(body: GroupIn, db: DB, actor: Actor = require("schedule", "create")) -> GroupOut:
    actor.ensure_branch("schedule", "create", body.branch_id)
    if await db.get(Level, body.level_id) is None:
        raise bad_request("Уровень не найден")
    await _check_teacher(db, body.teacher_id, body.branch_id)
    g = Group(**body.model_dump())
    g.capacity = min(g.capacity, KIND_CAPACITY.get(g.kind, g.capacity))
    db.add(g)
    await db.flush()
    await chats.ensure_group_chat(db, g)
    await write_audit(db, actor_id=actor.id, action="group.create", entity="group", entity_id=g.id, branch_id=g.branch_id,
                      ip=actor.ip, after=snapshot(g, ["name", "level_id", "teacher_id", "room_id"]))
    await db.commit()
    return await _group_out(db, g)


@router.get("/groups/{group_id}", response_model=GroupOut)
async def get_group(group_id: int, db: DB, actor: Actor = require("schedule", "view")) -> GroupOut:
    return await _group_out(db, await _get_group(db, actor, group_id))


@router.patch("/groups/{group_id}", response_model=GroupOut)
async def update_group(group_id: int, body: GroupIn, db: DB, actor: Actor = require("schedule", "edit")) -> GroupOut:
    g = await _get_group(db, actor, group_id)
    actor.ensure_branch("schedule", "edit", g.branch_id)
    if body.branch_id != g.branch_id:
        raise bad_request("Филиал группы не меняется — создайте новую группу и переведите учеников")
    before = snapshot(g, ["name", "level_id", "teacher_id", "room_id", "capacity", "status", "kind"])
    old_teacher = g.teacher_id
    if body.teacher_id != g.teacher_id:
        await _check_teacher(db, body.teacher_id, g.branch_id)
    for k, v in body.model_dump().items():
        setattr(g, k, v)
    g.capacity = min(g.capacity, KIND_CAPACITY.get(g.kind, g.capacity))
    if old_teacher != g.teacher_id:
        await chats.change_group_teacher(db, g, old_teacher)
        # Future planned lessons follow the new teacher.
        for lesson in await db.scalars(select(Lesson).where(Lesson.group_id == g.id, Lesson.starts_at > now(),
                                                             Lesson.status == LessonStatus.PLANNED, Lesson.teacher_id == old_teacher)):
            lesson.teacher_id = g.teacher_id
        for r in await db.scalars(select(ScheduleRule).where(ScheduleRule.group_id == g.id)):
            r.teacher_id = g.teacher_id
    await write_audit(db, actor_id=actor.id, action="group.update", entity="group", entity_id=g.id, branch_id=g.branch_id,
                      ip=actor.ip, before=before, after=snapshot(g, list(before)))
    try:
        await db.commit()
    except IntegrityError:
        raise conflict("У нового учителя пересекаются уроки — проверьте расписание") from None
    return await _group_out(db, g)


@router.post("/groups/{group_id}/archive", status_code=204)
async def archive_group(group_id: int, db: DB, actor: Actor = require("schedule", "edit")) -> None:
    g = await _get_group(db, actor, group_id)
    g.archived_at = now()
    g.status = "finished"
    for lesson in await db.scalars(select(Lesson).where(Lesson.group_id == g.id, Lesson.starts_at > now(),
                                                         Lesson.status == LessonStatus.PLANNED)):
        lesson.status, lesson.cancel_reason = LessonStatus.CANCELLED, "Группа закрыта"
    await write_audit(db, actor_id=actor.id, action="group.archive", entity="group", entity_id=g.id, branch_id=g.branch_id, ip=actor.ip)
    await db.commit()


class MemberIn(In):
    student_id: int


@router.get("/groups/{group_id}/members")
async def members(group_id: int, db: DB, actor: Actor = require("schedule", "view")) -> list[dict]:
    g = await _get_group(db, actor, group_id)
    rows = (await db.execute(
        select(GroupMember, Student).join(Student, Student.id == GroupMember.student_id)
        .where(GroupMember.group_id == g.id, GroupMember.left_on.is_(None)).order_by(Student.full_name)
    )).all()
    return [{"student_id": s.id, "full_name": s.full_name, "joined_on": m.joined_on, "lessons_left": s.lessons_left,
             "status": s.status} for m, s in rows]


@router.post("/groups/{group_id}/members", status_code=201)
async def add_member(group_id: int, body: MemberIn, db: DB, actor: Actor = require("students", "edit")) -> dict:
    """Enrol a student without a balance recalculation (first group, or same-price move handled via transfer)."""
    g = await _get_group(db, actor, group_id, "edit")
    s = await get_student_scoped(db, actor, body.student_id, "students", "edit")
    active = await db.scalar(select(GroupMember).where(GroupMember.student_id == s.id, GroupMember.left_on.is_(None)))
    if active is not None:
        raise conflict("Ученик уже в группе — используйте перевод")
    cnt = await db.scalar(select(func.count()).select_from(GroupMember).where(GroupMember.group_id == g.id,
                                                                                GroupMember.left_on.is_(None)))
    if cnt >= g.capacity:
        raise conflict(f"В группе нет мест ({cnt}/{g.capacity})")
    db.add(GroupMember(group_id=g.id, student_id=s.id, joined_on=today()))
    s.level_id = g.level_id
    if s.status in (StudentStatus.LEAD, StudentStatus.TRIAL):
        s.status = StudentStatus.ACTIVE
    await chats.sync_student_in_group_chat(db, g, s, True)
    await write_audit(db, actor_id=actor.id, action="group.member_add", entity="group", entity_id=g.id,
                      branch_id=g.branch_id, ip=actor.ip, after={"student_id": s.id})
    await db.commit()
    return {"ok": True}


@router.delete("/groups/{group_id}/members/{student_id}", status_code=204)
async def remove_member(group_id: int, student_id: int, db: DB, actor: Actor = require("students", "edit")) -> None:
    g = await _get_group(db, actor, group_id, "edit")
    m = await db.scalar(select(GroupMember).where(GroupMember.group_id == g.id, GroupMember.student_id == student_id,
                                                  GroupMember.left_on.is_(None)))
    if m is None:
        raise not_found("Ученик в группе")
    m.left_on = today()
    s = await db.get(Student, student_id)
    await chats.sync_student_in_group_chat(db, g, s, False)
    await write_audit(db, actor_id=actor.id, action="group.member_remove", entity="group", entity_id=g.id,
                      branch_id=g.branch_id, ip=actor.ip, before={"student_id": student_id})
    await db.commit()


class RuleIn(In):
    weekdays: list[int] = Field(min_length=1, max_length=7)
    start_time: time
    end_time: time
    room_id: int
    valid_from: date
    valid_to: date | None = None

    @model_validator(mode="after")
    def _check(self):
        if self.end_time <= self.start_time:
            raise ValueError("Время окончания должно быть позже начала")
        if any(d < 0 or d > 6 for d in self.weekdays):
            raise ValueError("Дни недели 0–6")
        return self


@router.post("/groups/{group_id}/schedule", status_code=201)
async def add_rule(group_id: int, body: RuleIn, db: DB, actor: Actor = require("schedule", "create")) -> dict:
    g = await _get_group(db, actor, group_id)
    actor.ensure_branch("schedule", "create", g.branch_id)
    room = await db.get(Room, body.room_id)
    if room is None or room.branch_id != g.branch_id or room.archived_at:
        raise bad_request("Кабинет не найден в филиале группы")
    if room.status != "active":
        raise bad_request("Кабинет на ремонте")
    if room.capacity < g.capacity:
        raise bad_request(f"Вместимость кабинета {room.capacity} меньше размера группы {g.capacity}")
    rule = ScheduleRule(group_id=g.id, weekdays=sorted(set(body.weekdays)), start_time=body.start_time, end_time=body.end_time,
                        room_id=room.id, teacher_id=g.teacher_id, valid_from=body.valid_from, valid_to=body.valid_to)
    db.add(rule)
    await db.flush()
    created, problems = await sched.generate(db, rule, g)
    if created == 0 and problems:
        # Nothing could be scheduled: don't keep a rule that only produces conflicts.
        await db.delete(rule)
        await db.commit()
        raise conflict(f"Все занятия пересекаются с расписанием: {problems[0]}" + (f" и ещё {len(problems) - 1}" if len(problems) > 1 else ""))
    await write_audit(db, actor_id=actor.id, action="schedule.rule_add", entity="group", entity_id=g.id, branch_id=g.branch_id,
                      ip=actor.ip, after={"weekdays": rule.weekdays, "time": f"{body.start_time}-{body.end_time}", "lessons": created})
    await db.commit()
    return {"rule_id": rule.id, "created": created, "conflicts": problems}


@router.delete("/schedule-rules/{rule_id}", status_code=204)
async def end_rule(rule_id: int, db: DB, actor: Actor = require("schedule", "edit")) -> None:
    rule = await db.get(ScheduleRule, rule_id)
    if rule is None:
        raise not_found("Расписание")
    g = await _get_group(db, actor, rule.group_id)
    rule.archived_at, rule.valid_to = now(), today()
    for lesson in await db.scalars(select(Lesson).where(Lesson.rule_id == rule.id, Lesson.starts_at > now(),
                                                         Lesson.status == LessonStatus.PLANNED)):
        lesson.status, lesson.cancel_reason = LessonStatus.CANCELLED, "Расписание изменено"
    await write_audit(db, actor_id=actor.id, action="schedule.rule_end", entity="group", entity_id=g.id, branch_id=g.branch_id, ip=actor.ip)
    await db.commit()


# ---------- lessons ----------
class LessonOut(ORM):
    id: int
    branch_id: int
    group_id: int | None
    student_id: int | None
    level_id: int | None
    teacher_id: int
    actual_teacher_id: int | None
    room_id: int
    starts_at: datetime
    ends_at: datetime
    status: str
    cancel_reason: str | None
    attendance_marked_at: datetime | None
    topic: str | None
    group_name: str | None = None
    # group | duo | individual: lessons of an individual student (no group) are «individual»
    kind: str = "group"
    teacher_name: str | None = None
    room_name: str | None = None
    trials: int = 0


def lesson_filter(actor: Actor):
    """Lessons visible through the schedule, or — for attendance-only roles — through attendance."""
    module = "schedule" if actor.can("schedule", "view") else "attendance"
    scope = actor.scope(module, "view")
    if scope == NETWORK:
        return true()
    if scope == OWN:
        return or_(Lesson.teacher_id == actor.id, Lesson.actual_teacher_id == actor.id)
    return Lesson.branch_id.in_(actor.branch_ids or {-1})


async def _lesson_outs(db: DB, lessons: list[Lesson]) -> list[LessonOut]:
    gids = {x.group_id for x in lessons if x.group_id}
    uids = {x.teacher_id for x in lessons} | {x.actual_teacher_id for x in lessons if x.actual_teacher_id}
    rids = {x.room_id for x in lessons}
    grows = (await db.execute(select(Group.id, Group.name, Group.kind).where(Group.id.in_(gids)))).all() if gids else []
    gn = {i: n for i, n, _ in grows}
    gk = {i: k for i, _, k in grows}
    un = dict((await db.execute(select(User.id, User.full_name).where(User.id.in_(uids)))).all()) if uids else {}
    rn = dict((await db.execute(select(Room.id, Room.name).where(Room.id.in_(rids)))).all()) if rids else {}
    lids = [x.id for x in lessons]
    trials = dict((await db.execute(select(Lead.trial_lesson_id, func.count()).where(Lead.trial_lesson_id.in_(lids))
                                    .group_by(Lead.trial_lesson_id))).all()) if lids else {}
    out = []
    for x in lessons:
        o = LessonOut.model_validate(x)
        o.group_name = gn.get(x.group_id) if x.group_id else "Индивидуально"
        o.kind = gk.get(x.group_id, "group") if x.group_id else "individual"
        o.teacher_name = un.get(x.actual_teacher_id or x.teacher_id)
        o.room_name = rn.get(x.room_id)
        o.trials = trials.get(x.id, 0)
        out.append(o)
    return out


@router.get("/lessons", response_model=list[LessonOut])
async def list_lessons(
    db: DB, actor: Actor = require_staff(), date_from: date = Query(alias="from"), date_to: date = Query(alias="to"),
    branch_id: int | None = None, room_id: int | None = None, teacher_id: int | None = None, group_id: int | None = None,
    include_cancelled: bool = False, kind: str | None = Query(default=None, pattern="^(group|duo|individual)$"),
) -> list[LessonOut]:
    if not (actor.can("schedule", "view") or actor.can("attendance", "view")):
        raise forbidden()
    if (date_to - date_from).days > 62:
        raise bad_request("Период не больше 2 месяцев")
    from app.services.clock import local_range

    start, end = local_range(date_from, date_to)
    q = select(Lesson).where(lesson_filter(actor), Lesson.starts_at >= start, Lesson.starts_at < end)
    if not include_cancelled:
        q = q.where(Lesson.status != LessonStatus.CANCELLED)
    if branch_id:
        q = q.where(Lesson.branch_id == branch_id)
    if room_id:
        q = q.where(Lesson.room_id == room_id)
    if teacher_id:
        q = q.where(or_(Lesson.teacher_id == teacher_id, Lesson.actual_teacher_id == teacher_id))
    if group_id:
        q = q.where(Lesson.group_id == group_id)
    if kind == "individual":
        q = q.where(or_(Lesson.group_id.is_(None), Lesson.group_id.in_(select(Group.id).where(Group.kind == "individual"))))
    elif kind:
        q = q.where(Lesson.group_id.in_(select(Group.id).where(Group.kind == kind)))
    return await _lesson_outs(db, list(await db.scalars(q.order_by(Lesson.starts_at).limit(3000))))


class LessonIn(In):
    group_id: int | None = None
    student_id: int | None = None
    teacher_id: int
    room_id: int
    starts_at: datetime
    ends_at: datetime
    topic: str | None = Field(default=None, max_length=255)


@router.post("/lessons", response_model=LessonOut, status_code=201)
async def create_lesson(body: LessonIn, db: DB, actor: Actor = require("schedule", "create")) -> LessonOut:
    if body.ends_at <= body.starts_at:
        raise bad_request("Время окончания должно быть позже начала")
    room = await db.get(Room, body.room_id)
    if room is None:
        raise bad_request("Кабинет не найден")
    actor.ensure_branch("schedule", "create", room.branch_id)
    await _check_teacher(db, body.teacher_id, room.branch_id)
    level_id = None
    if body.group_id:
        g = await _get_group(db, actor, body.group_id)
        level_id = g.level_id
    elif body.student_id:
        s = await get_student_scoped(db, actor, body.student_id)
        level_id = s.level_id
    else:
        raise bad_request("Укажите группу или ученика")
    if c := await sched.conflicts(db, room_id=room.id, teacher_id=body.teacher_id, starts_at=body.starts_at, ends_at=body.ends_at):
        raise conflict(c[0])
    lesson = Lesson(branch_id=room.branch_id, group_id=body.group_id, student_id=body.student_id, level_id=level_id,
                    teacher_id=body.teacher_id, room_id=room.id, starts_at=body.starts_at, ends_at=body.ends_at, topic=body.topic)
    db.add(lesson)
    try:
        await db.flush()
    except IntegrityError:
        raise conflict("Кабинет или учитель заняты в это время") from None
    await write_audit(db, actor_id=actor.id, action="lesson.create", entity="lesson", entity_id=lesson.id,
                      branch_id=lesson.branch_id, ip=actor.ip)
    await db.commit()
    return (await _lesson_outs(db, [lesson]))[0]


async def _get_lesson(db: DB, actor: Actor, lesson_id: int) -> Lesson:
    lesson = await db.scalar(select(Lesson).where(Lesson.id == lesson_id, lesson_filter(actor)))
    if lesson is None:
        raise not_found("Урок")
    return lesson


async def _notify_group(db: DB, lesson: Lesson, code: str, variables: dict) -> None:
    if not lesson.group_id:
        if lesson.student_id:
            s = await db.get(Student, lesson.student_id)
            await notify_guardians(db, s, code, variables, ref=("lesson", lesson.id))
        return
    students = await db.scalars(select(Student).join(GroupMember, GroupMember.student_id == Student.id)
                                .where(GroupMember.group_id == lesson.group_id, GroupMember.left_on.is_(None)))
    for s in students:
        await notify_guardians(db, s, code, variables, ref=("lesson", lesson.id))


class CancelIn(In):
    reason: str = Field(min_length=3, max_length=255)


@router.post("/lessons/{lesson_id}/cancel", response_model=LessonOut)
async def cancel_lesson(lesson_id: int, body: CancelIn, db: DB, actor: Actor = require("schedule", "edit")) -> LessonOut:
    lesson = await _get_lesson(db, actor, lesson_id)
    actor.ensure_branch("schedule", "edit", lesson.branch_id)
    if lesson.status != LessonStatus.PLANNED:
        raise bad_request("Отменить можно только запланированный урок")
    lesson.status, lesson.cancel_reason = LessonStatus.CANCELLED, body.reason
    g = await db.get(Group, lesson.group_id) if lesson.group_id else None
    loc = local(lesson.starts_at)
    await _notify_group(db, lesson, "lesson_cancel", {"group": g.name if g else "", "date": f"{loc:%d.%m}",
                                                      "time": f"{loc:%H:%M}", "reason": body.reason})
    await write_audit(db, actor_id=actor.id, action="lesson.cancel", entity="lesson", entity_id=lesson.id,
                      branch_id=lesson.branch_id, ip=actor.ip, after={"reason": body.reason})
    await db.commit()
    return (await _lesson_outs(db, [lesson]))[0]


class MoveIn(In):
    starts_at: datetime
    ends_at: datetime
    room_id: int | None = None
    reason: str = Field(min_length=3, max_length=255)


@router.post("/lessons/{lesson_id}/move", response_model=LessonOut)
async def move_lesson(lesson_id: int, body: MoveIn, db: DB, actor: Actor = require("schedule", "edit")) -> LessonOut:
    old = await _get_lesson(db, actor, lesson_id)
    actor.ensure_branch("schedule", "edit", old.branch_id)
    if old.status != LessonStatus.PLANNED:
        raise bad_request("Перенести можно только запланированный урок")
    if body.ends_at <= body.starts_at:
        raise bad_request("Время окончания должно быть позже начала")
    room_id = body.room_id or old.room_id
    teacher = old.actual_teacher_id or old.teacher_id
    if c := await sched.conflicts(db, room_id=room_id, teacher_id=teacher, starts_at=body.starts_at, ends_at=body.ends_at,
                                  exclude_id=old.id):
        raise conflict(c[0])
    old.status, old.cancel_reason = LessonStatus.CANCELLED, f"Перенос: {body.reason}"
    await db.flush()
    new = Lesson(branch_id=old.branch_id, group_id=old.group_id, student_id=old.student_id, level_id=old.level_id,
                 teacher_id=old.teacher_id, actual_teacher_id=old.actual_teacher_id, room_id=room_id,
                 starts_at=body.starts_at, ends_at=body.ends_at, moved_from_id=old.id, topic=old.topic)
    db.add(new)
    try:
        await db.flush()
    except IntegrityError:
        raise conflict("Кабинет или учитель заняты в это время") from None
    for lead in await db.scalars(select(Lead).where(Lead.trial_lesson_id == old.id)):
        lead.trial_lesson_id = new.id
    g = await db.get(Group, old.group_id) if old.group_id else None
    loc = local(new.starts_at)
    await _notify_group(db, new, "lesson_move", {"group": g.name if g else "", "date": f"{loc:%d.%m}", "time": f"{loc:%H:%M}",
                                                 "reason": body.reason})
    await write_audit(db, actor_id=actor.id, action="lesson.move", entity="lesson", entity_id=old.id, branch_id=old.branch_id,
                      ip=actor.ip, before={"starts_at": old.starts_at.isoformat()}, after={"lesson_id": new.id, "starts_at": new.starts_at.isoformat()})
    await db.commit()
    return (await _lesson_outs(db, [new]))[0]


class SubstituteIn(In):
    teacher_id: int


@router.post("/lessons/{lesson_id}/substitute", response_model=LessonOut)
async def substitute(lesson_id: int, body: SubstituteIn, db: DB, actor: Actor = require("schedule", "edit")) -> LessonOut:
    """ТЗ 4.2: the lesson is paid to the teacher who actually taught it."""
    lesson = await _get_lesson(db, actor, lesson_id)
    actor.ensure_branch("schedule", "edit", lesson.branch_id)
    await _check_teacher(db, body.teacher_id, lesson.branch_id)
    if c := await sched.conflicts(db, room_id=-1, teacher_id=body.teacher_id, starts_at=lesson.starts_at,
                                  ends_at=lesson.ends_at, exclude_id=lesson.id):
        raise conflict(c[0])
    before = lesson.actual_teacher_id
    lesson.actual_teacher_id = None if body.teacher_id == lesson.teacher_id else body.teacher_id
    await write_audit(db, actor_id=actor.id, action="lesson.substitute", entity="lesson", entity_id=lesson.id,
                      branch_id=lesson.branch_id, ip=actor.ip, before={"actual_teacher_id": before},
                      after={"actual_teacher_id": lesson.actual_teacher_id})
    await db.commit()
    return (await _lesson_outs(db, [lesson]))[0]


# ---------- attendance (ТЗ 7.1) ----------
class RosterRow(In):
    student_id: int | None
    lead_id: int | None
    full_name: str = Field(max_length=255)
    is_trial: bool
    status: str | None = Field(max_length=255)
    grade: int | None
    comment: str | None = Field(max_length=4000)
    stars: int
    lessons_left: int | None
    frozen: bool = False
    blocked: bool = False


class Roster(BaseModel):
    lesson: LessonOut
    can_edit: bool
    needs_reason: bool
    rows: list[RosterRow]


async def _edit_rights(db: DB, actor: Actor, lesson: Lesson) -> tuple[bool, bool]:
    """(can_edit, needs_reason). The teacher marks from the lesson start until the end of the window — setting
    «attendance_teacher_window»: "same_day" (default) or a number of hours after the lesson ends; later only
    staff with attendance.edit_past, always with a reason (ТЗ 7.1, 10.5)."""
    t = now()
    is_teacher = actor.id in (lesson.teacher_id, lesson.actual_teacher_id)
    window = await setting(db, "attendance_teacher_window")
    closes = (lesson.ends_at + timedelta(hours=int(window)) if str(window).isdigit()
              else end_of_local_day(lesson.starts_at))
    in_window = lesson.starts_at - timedelta(minutes=15) <= t < closes
    if actor.can("attendance", "mark") and in_window:
        scope = actor.scope("attendance", "mark")
        if scope != OWN or is_teacher:
            return True, False
    if actor.can("attendance", "edit_past") and t >= lesson.starts_at - timedelta(minutes=15):
        if actor.scope("attendance", "edit_past") == NETWORK or lesson.branch_id in actor.branch_ids:
            return True, not in_window or lesson.attendance_marked_at is not None
    return False, False


@router.get("/lessons/{lesson_id}/attendance", response_model=Roster)
async def roster(lesson_id: int, db: DB, actor: Actor = require("attendance", "view")) -> Roster:
    lesson = await _get_lesson(db, actor, lesson_id)
    marks = {(a.student_id, a.lead_id): a for a in await db.scalars(select(Attendance).where(Attendance.lesson_id == lesson.id))}
    d = local(lesson.starts_at).date()
    rows: list[RosterRow] = []
    if lesson.group_id:
        students = list(await db.scalars(
            select(Student).join(GroupMember, GroupMember.student_id == Student.id)
            .where(GroupMember.group_id == lesson.group_id, GroupMember.joined_on <= d,
                   or_(GroupMember.left_on.is_(None), GroupMember.left_on > d)).order_by(Student.full_name)))
    else:
        students = [await db.get(Student, lesson.student_id)] if lesson.student_id else []
    seen = set()
    for s in students:
        seen.add(s.id)
        a = marks.get((s.id, None))
        rows.append(RosterRow(student_id=s.id, lead_id=None, full_name=s.full_name, is_trial=False,
                              status=a.status if a else None, grade=a.grade if a else None, comment=a.comment if a else None,
                              stars=a.stars if a else 0, lessons_left=s.lessons_left, frozen=await is_frozen_on(db, s.id, d),
                              blocked=s.access_blocked_at is not None))
    for (sid, lid), a in marks.items():
        if sid and sid not in seen:  # student who left the group after being marked
            s = await db.get(Student, sid)
            rows.append(RosterRow(student_id=sid, lead_id=None, full_name=s.full_name, is_trial=False, status=a.status,
                                  grade=a.grade, comment=a.comment, stars=a.stars, lessons_left=s.lessons_left))
    for lead in await db.scalars(select(Lead).where(Lead.trial_lesson_id == lesson.id, Lead.archived_at.is_(None))):
        a = marks.get((None, lead.id))
        rows.append(RosterRow(student_id=None, lead_id=lead.id, full_name=lead.full_name, is_trial=True,
                              status=a.status if a else None, grade=None, comment=a.comment if a else None, stars=0,
                              lessons_left=None))
    can_edit, needs_reason = await _edit_rights(db, actor, lesson)
    return Roster(lesson=(await _lesson_outs(db, [lesson]))[0], can_edit=can_edit, needs_reason=needs_reason, rows=rows)


class MarkIn(In):
    student_id: int | None = None
    lead_id: int | None = None
    status: str = Field(max_length=255)
    grade: int | None = Field(default=None, ge=1, le=5)
    comment: str | None = Field(default=None, max_length=500)
    stars: int = Field(default=0, ge=0, le=5)


class MarksIn(In):
    marks: list[MarkIn]
    reason: str | None = Field(default=None, max_length=255)
    topic: str | None = Field(default=None, max_length=255)


def _charged(status: str, charge_absent: bool, charge_late: bool) -> bool:
    return status == AttendanceStatus.PRESENT or (status == AttendanceStatus.LATE and charge_late) or (
        status == AttendanceStatus.ABSENT and charge_absent)


@router.put("/lessons/{lesson_id}/attendance", response_model=Roster)
async def mark(lesson_id: int, body: MarksIn, db: DB, actor: Actor = require("attendance", "view")) -> Roster:
    lesson = await _get_lesson(db, actor, lesson_id)
    if lesson.status == LessonStatus.CANCELLED:
        raise bad_request("Урок отменён")
    can_edit, needs_reason = await _edit_rights(db, actor, lesson)
    if not can_edit:
        raise forbidden("Отметка закрыта: исправить может администратор с указанием причины")
    if needs_reason and not body.reason:
        raise bad_request("Укажите причину исправления")
    charge_absent = bool(await setting(db, "charge_unexcused_absence"))
    charge_late = bool(await setting(db, "charge_late"))
    trial_counts = bool(await setting(db, "trial_counts_in_n"))
    group = await db.get(Group, lesson.group_id) if lesson.group_id else None
    loc = local(lesson.starts_at)
    allowed_students = {r.student_id for r in (await roster(lesson.id, db, actor)).rows if r.student_id}
    allowed_leads = set((await db.scalars(select(Lead.id).where(Lead.trial_lesson_id == lesson.id))).all())
    changes = []
    for m in body.marks:
        if m.status not in AttendanceStatus.ALL:
            raise bad_request(f"Неизвестный статус {m.status}")
        if (m.student_id is None) == (m.lead_id is None):
            raise bad_request("Укажите ученика или пробного")
        if m.student_id and m.student_id not in allowed_students:
            raise bad_request("Ученик не из этого урока")
        if m.lead_id and m.lead_id not in allowed_leads:
            raise bad_request("Пробный не записан на этот урок")
        a = await db.scalar(select(Attendance).where(Attendance.lesson_id == lesson.id,
                                                     Attendance.student_id == m.student_id if m.student_id else Attendance.lead_id == m.lead_id))
        old_status = a.status if a else None
        if a is None:
            a = Attendance(lesson_id=lesson.id, student_id=m.student_id, lead_id=m.lead_id, status=m.status, marked_by=actor.id)
            db.add(a)
        a.status, a.grade, a.comment, a.marked_by = m.status, m.grade, m.comment, actor.id
        if m.student_id:
            s = await db.get(Student, m.student_id)
            if await is_frozen_on(db, s.id, loc.date()):
                want = False  # ТЗ 5.3: frozen students are not charged
            else:
                want = _charged(m.status, charge_absent, charge_late)
            star_delta = m.stars - a.stars
            a.stars = m.stars
            s.stars += star_delta
            if want != a.charged:
                await bal.apply(db, s, "lesson", lessons=-1 if want else 1, price=s.balance_lesson_price,
                                ref=("attendance", lesson.id), actor_id=actor.id, counts_as_done=True,
                                note=f"{'Урок' if want else 'Возврат урока'} {loc:%d.%m %H:%M}")
                a.charged = want
            if m.status in (AttendanceStatus.PRESENT, AttendanceStatus.LATE):
                s.last_visit_at = max(s.last_visit_at or lesson.starts_at, lesson.starts_at)
                await award_auto(db, s.id, "attendance", ("lesson", lesson.id), "Посещение урока")
            if old_status != m.status:
                variables = {"time": f"{loc:%H:%M}", "group": group.name if group else ""}
                if m.status == AttendanceStatus.ABSENT:
                    await notify_guardians(db, s, "absence", variables, ref=("attendance", lesson.id))
                elif m.status == AttendanceStatus.PRESENT and await setting(db, "notify_present"):
                    await notify_guardians(db, s, "present", variables, ref=("attendance", lesson.id))
                elif m.status == AttendanceStatus.LATE and await setting(db, "notify_late"):
                    await notify_guardians(db, s, "late", variables, ref=("attendance", lesson.id))
                low = int(await setting(db, "low_balance_lessons") or 2)
                if a.charged and s.lessons_left == low:
                    await notify_guardians(db, s, "pay_reminder", {"left": s.lessons_left}, ref=("low_balance", lesson.id))
        else:
            lead = await db.get(Lead, m.lead_id)
            if m.status in (AttendanceStatus.PRESENT, AttendanceStatus.LATE):
                await crm.on_trial_attended(db, lead, lesson, actor.id)
        if old_status != m.status:
            changes.append({"student_id": m.student_id, "lead_id": m.lead_id, "from": old_status, "to": m.status})
    await db.flush()
    # Lesson held → teacher pay. N = present + late (+ trial visitors if configured).
    all_marks = list(await db.scalars(select(Attendance).where(Attendance.lesson_id == lesson.id)))
    n = sum(1 for x in all_marks if x.status in (AttendanceStatus.PRESENT, AttendanceStatus.LATE)
            and (x.student_id or trial_counts))
    first_mark = lesson.attendance_marked_at is None
    lesson.status = LessonStatus.DONE
    lesson.attendance_marked_at = lesson.attendance_marked_at or now()
    if body.topic:
        lesson.topic = body.topic
    await accrue_lesson(db, teacher_id=lesson.actual_teacher_id or lesson.teacher_id, lesson_id=lesson.id, n=n,
                        on=loc.date(), branch_id=lesson.branch_id, group_name=group.name if group else "индивидуально",
                        actor_id=actor.id, kind=group.kind if group else "individual")
    await write_audit(db, actor_id=actor.id, action="attendance.mark" if first_mark and not needs_reason else "attendance.fix",
                      entity="lesson", entity_id=lesson.id, branch_id=lesson.branch_id, ip=actor.ip,
                      after={"changes": changes, "n": n}, note=body.reason)
    await db.commit()
    return await roster(lesson.id, db, actor)


# ---------- homework ----------
class HomeworkIn(In):
    title: str = Field(min_length=2, max_length=255)
    body: str | None = Field(default=None, max_length=8000)
    due_at: datetime | None = None
    lesson_id: int | None = None


class HomeworkOut(ORM):
    id: int
    group_id: int
    lesson_id: int | None
    title: str
    body: str | None
    due_at: datetime | None
    created_at: datetime
    submitted: int = 0
    checked: int = 0


@router.get("/groups/{group_id}/homework", response_model=list[HomeworkOut])
async def list_homework(group_id: int, db: DB, actor: Actor = require("homework", "view")) -> list[HomeworkOut]:
    g = await _get_group(db, actor, group_id)
    out = []
    for h in await db.scalars(select(Homework).where(Homework.group_id == g.id, Homework.archived_at.is_(None))
                              .order_by(Homework.id.desc()).limit(100)):
        o = HomeworkOut.model_validate(h)
        subs = list(await db.scalars(select(HomeworkSubmission.status).where(HomeworkSubmission.homework_id == h.id)))
        o.submitted, o.checked = len(subs), sum(1 for x in subs if x == "checked")
        out.append(o)
    return out


@router.post("/groups/{group_id}/homework", response_model=HomeworkOut, status_code=201)
async def add_homework(group_id: int, body: HomeworkIn, db: DB, actor: Actor = require("homework", "manage")) -> HomeworkOut:
    g = await _get_group(db, actor, group_id)
    if actor.scope("homework", "manage") == OWN and g.teacher_id != actor.id:
        raise forbidden()
    h = Homework(group_id=g.id, created_by=actor.id, **body.model_dump())
    db.add(h)
    await db.flush()
    await write_audit(db, actor_id=actor.id, action="homework.create", entity="homework", entity_id=h.id, branch_id=g.branch_id, ip=actor.ip)
    await db.commit()
    return HomeworkOut.model_validate(h)


class HomeworkPatch(In):
    title: str | None = Field(default=None, min_length=2, max_length=255)
    body: str | None = Field(default=None, max_length=8000)
    due_at: datetime | None = None
    lesson_id: int | None = None


async def _homework_for(db: DB, actor: Actor, homework_id: int, action: str) -> tuple[Homework, Group]:
    h = await db.get(Homework, homework_id)
    if h is None or h.archived_at:
        raise not_found("Задание")
    g = await _get_group(db, actor, h.group_id)
    if actor.scope("homework", action) == OWN and g.teacher_id != actor.id:
        raise not_found("Задание")
    return h, g


@router.get("/homework/{homework_id}/submissions")
async def submissions(homework_id: int, db: DB, actor: Actor = require("homework", "view")) -> list[dict]:
    """One row per active member: the teacher sees who handed in what."""
    h, g = await _homework_for(db, actor, homework_id, "view")
    rows = (await db.execute(
        select(Student.id, Student.full_name, HomeworkSubmission).join(GroupMember, GroupMember.student_id == Student.id)
        .outerjoin(HomeworkSubmission, (HomeworkSubmission.homework_id == h.id) & (HomeworkSubmission.student_id == Student.id))
        .where(GroupMember.group_id == g.id, GroupMember.left_on.is_(None)).order_by(Student.full_name))).all()
    from app.services import files

    return [{"student_id": sid, "full_name": name, "status": sub.status if sub else "assigned",
             "answer": sub.answer if sub else None, "file_url": files.signed_url(sub.file_url) if sub else None,
             "grade": sub.grade if sub else None, "teacher_comment": sub.teacher_comment if sub else None,
             "submitted_at": sub.updated_at if sub else None} for sid, name, sub in rows]


@router.patch("/homework/{homework_id}", response_model=HomeworkOut)
async def edit_homework(homework_id: int, body: HomeworkPatch, db: DB, actor: Actor = require("homework", "manage")) -> HomeworkOut:
    h, g = await _homework_for(db, actor, homework_id, "manage")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(h, k, v)
    await write_audit(db, actor_id=actor.id, action="homework.update", entity="homework", entity_id=h.id, branch_id=g.branch_id,
                      ip=actor.ip, after=body.model_dump(mode="json", exclude_unset=True))
    await db.commit()
    return HomeworkOut.model_validate(h)


@router.post("/homework/{homework_id}/archive", status_code=204)
async def archive_homework(homework_id: int, db: DB, actor: Actor = require("homework", "manage")) -> None:
    h, g = await _homework_for(db, actor, homework_id, "manage")
    h.archived_at = now()
    await write_audit(db, actor_id=actor.id, action="homework.archive", entity="homework", entity_id=h.id, branch_id=g.branch_id,
                      ip=actor.ip)
    await db.commit()


class CheckIn(In):
    grade: int | None = Field(default=None, ge=1, le=5)
    comment: str | None = Field(default=None, max_length=1000)


@router.put("/homework/{homework_id}/submissions/{student_id}", status_code=204)
async def check_submission(homework_id: int, student_id: int, body: CheckIn, db: DB,
                           actor: Actor = require("homework", "manage")) -> None:
    h = await db.get(Homework, homework_id)
    if h is None:
        raise not_found("Задание")
    g = await _get_group(db, actor, h.group_id)
    if actor.scope("homework", "manage") == OWN and g.teacher_id != actor.id:
        raise forbidden()
    if not await db.scalar(select(GroupMember.id).where(GroupMember.group_id == g.id, GroupMember.student_id == student_id)):
        raise not_found("Ученик в группе")
    sub = await db.scalar(select(HomeworkSubmission).where(HomeworkSubmission.homework_id == h.id,
                                                           HomeworkSubmission.student_id == student_id))
    if sub is None:
        sub = HomeworkSubmission(homework_id=h.id, student_id=student_id)
        db.add(sub)
    sub.status, sub.grade, sub.teacher_comment = "checked", body.grade, body.comment
    await award_auto(db, student_id, "homework", ("homework", h.id), "Домашнее задание")
    await db.commit()
