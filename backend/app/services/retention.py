"""Keeping students: follow-up tasks for the methodist (two absences in a row, a student who wants to leave)."""

from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Role, Student, Task, TaskAssignee, User, UserBranch
from app.models.identity import UserRole
from app.models.work import TaskStatus
from app.services.clock import local, now
from app.services.messaging import notify_user

OPEN = (TaskStatus.NEW, TaskStatus.IN_PROGRESS, TaskStatus.REVIEW)


async def _with_role(db: AsyncSession, cond) -> list[tuple[int, set[int]]]:
    """Active staff holding a role that matches `cond` → [(user id, their branch ids)]."""
    ids = list(await db.scalars(
        select(User.id).join(UserRole, UserRole.user_id == User.id).join(Role, Role.id == UserRole.role_id)
        .where(cond, Role.archived_at.is_(None), User.is_active.is_(True), User.archived_at.is_(None)).distinct()))
    out = []
    for uid in ids:
        out.append((uid, set(await db.scalars(select(UserBranch.branch_id).where(UserBranch.user_id == uid)))))
    return out


async def methodists(db: AsyncSession, branch_id: int | None) -> list[int]:
    """Who gets the follow-up tasks: staff with the «Методист» role (of the student's branch when there are
    several). Without such a role in the school, the owner."""
    people = await _with_role(db, func.lower(Role.name).like("%методист%"))
    if people:
        mine = [uid for uid, br in people if not br or branch_id in br]
        return mine or [uid for uid, _ in people]
    return [uid for uid, _ in await _with_role(db, Role.code == "owner")]


async def branch_admins(db: AsyncSession, branch_id: int | None) -> list[int]:
    """Branch admins of the student's branch; without one, the owner."""
    people = await _with_role(db, Role.code == "branch_admin")
    mine = [uid for uid, br in people if branch_id in br]
    return mine or [uid for uid, _ in await _with_role(db, Role.code == "owner")]


async def is_methodist(db: AsyncSession, user_id: int) -> bool:
    return bool(await db.scalar(
        select(UserRole.id).join(Role, Role.id == UserRole.role_id)
        .where(UserRole.user_id == user_id, func.lower(Role.name).like("%методист%"), Role.archived_at.is_(None)).limit(1)))


async def has_methodists(db: AsyncSession) -> bool:
    return bool(await _with_role(db, func.lower(Role.name).like("%методист%")))


async def open_task(db: AsyncSession, student_id: int, auto_kind: str) -> Task | None:
    return await db.scalar(select(Task).where(
        Task.auto_kind == auto_kind, Task.link_type == "student", Task.link_id == student_id,
        Task.status.in_(OPEN), Task.archived_at.is_(None)).order_by(Task.id.desc()))


async def follow_up(db: AsyncSession, s: Student, auto_kind: str, title: str, description: str | None,
                    creator_id: int, hours: int = 24, who: list[int] | None = None, due_at=None) -> Task | None:
    """One open task of a kind per student: a second trigger does not make a duplicate.
    Goes to the methodists unless `who` names other people."""
    if await open_task(db, s.id, auto_kind):
        return None
    if who is None:
        who = await methodists(db, s.branch_id)
    if not who:
        return None
    t = Task(title=title[:255], description=description, creator_id=creator_id, branch_id=s.branch_id, priority="high",
             due_at=due_at or now() + timedelta(hours=hours), status=TaskStatus.NEW, link_type="student", link_id=s.id,
             auto_kind=auto_kind)
    db.add(t)
    await db.flush()
    for uid in who:
        db.add(TaskAssignee(task_id=t.id, user_id=uid))
        await notify_user(db, uid, "task", f"Новая задача: {t.title}", link=f"/tasks/{t.id}")
    return t


async def close_tasks(db: AsyncSession, student_id: int, auto_kind: str) -> None:
    for t in await db.scalars(select(Task).where(
            Task.auto_kind == auto_kind, Task.link_type == "student", Task.link_id == student_id, Task.status.in_(OPEN))):
        t.status, t.done_at = TaskStatus.DONE, now()


async def leave_groups(db: AsyncSession, s: Student, last_day: date) -> int:
    """A student who left is in their groups up to and including `last_day`: from the next day they are not on the
    attendance list. Attendance already marked stays as it is."""
    from app.models import Group, GroupMember
    from app.services import chats

    n = 0
    for m in await db.scalars(select(GroupMember).where(GroupMember.student_id == s.id, GroupMember.left_on.is_(None))):
        m.left_on = max(last_day + timedelta(days=1), m.joined_on)
        g = await db.get(Group, m.group_id)
        if g is not None:
            await chats.sync_student_in_group_chat(db, g, s, False)
        n += 1
    return n


async def rejoin_groups(db: AsyncSession, s: Student, last_day: date) -> int:
    """The student did not leave after all: the groups closed by leave_groups for that day are theirs again."""
    from app.models import Group, GroupMember
    from app.services import chats

    n = 0
    for m in await db.scalars(select(GroupMember).where(
            GroupMember.student_id == s.id, GroupMember.left_on == last_day + timedelta(days=1))):
        g = await db.get(Group, m.group_id)
        if g is None or g.archived_at is not None:
            continue
        m.left_on = None
        await chats.sync_student_in_group_chat(db, g, s, True)
        n += 1
    return n


async def no_trial_bonus(db: AsyncSession, user_id: int) -> bool:
    """Owner, 23.11.2026: a branch admin or office manager is not paid for a trial visit, only for the
    sale where he is the seller.
    The sales department keeps the trial bonus (also when the same person holds both roles)."""
    codes = set((await db.scalars(select(Role.code).join(UserRole, UserRole.role_id == Role.id)
                                  .where(UserRole.user_id == user_id, Role.archived_at.is_(None)))).all())
    return bool(codes & {"branch_admin", "office_manager"}) and "sales" not in codes


async def return_card(db: AsyncSession, s: Student, actor_id: int | None, stage: str = "left", why: str | None = None):
    """Owner, 27.11.2026: a student who left is at once a card in the «Возврат» funnel, worked like any lead (tasks,
    stages). One open card per student: asked again, the card is found and only moved forward when the school now
    knows more (may come back → «Связались», a return day is set → «Договорились»)."""
    from app.models import Lead, LeadEvent, LeadStage, Pipeline
    from app.modules.crm.service import create_lead
    from app.services import crm

    lead = await db.scalar(
        select(Lead).join(Pipeline, Pipeline.id == Lead.pipeline_id).join(LeadStage, LeadStage.id == Lead.stage_id)
        .where(Lead.student_id == s.id, Pipeline.code == "return", Lead.archived_at.is_(None),
               LeadStage.is_won.is_(False), LeadStage.is_lost.is_(False)).order_by(Lead.id.desc()).limit(1))
    target = await crm.stage_by_code(db, "return", stage) or await crm.stage_by_code(db, "return", "left")
    if target is None:
        return None  # the school removed the funnel
    if lead is None:
        seller = await db.get(User, s.sales_user_id) if s.sales_user_id else None
        if seller is not None and (not seller.is_active or seller.archived_at is not None):
            seller = None
        lead = await create_lead(db, full_name=s.full_name, phone=s.phone, branch_id=s.branch_id, source="return",
                                 owner_id=None, assignee_id=seller.id if seller else None, pipeline="return",
                                 stage=target.code, student_id=s.id, level_id=s.level_id, notify=False)
        if why:
            db.add(LeadEvent(lead_id=lead.id, at=now(), kind="note", text=why, actor_id=actor_id, meta={}))
    elif lead.stage_id != target.id:
        cur = await db.get(LeadStage, lead.stage_id)
        if cur is not None and target.order > cur.order:
            await crm.move(db, lead, target, actor_id, why)
    return lead


async def open_return_card(db: AsyncSession, student_id: int):
    """The student's open card in «Возврат», if any. The student's own lead link (students.lead_id) stays the lead
    of the first sale: a refund of that payment still cancels the bonuses tied to it."""
    from app.models import Lead, LeadStage, Pipeline

    return await db.scalar(
        select(Lead).join(Pipeline, Pipeline.id == Lead.pipeline_id).join(LeadStage, LeadStage.id == Lead.stage_id)
        .where(Lead.student_id == student_id, Pipeline.code == "return", Lead.archived_at.is_(None),
               LeadStage.is_won.is_(False), LeadStage.is_lost.is_(False)).order_by(Lead.id.desc()).limit(1))


async def close_return_card(db: AsyncSession, s: Student, actor_id: int | None, why: str) -> None:
    """The student did not leave after all (or is studying again without a payment): the open card leaves the funnel."""
    from app.models import Lead, LeadEvent, LeadStage, Pipeline

    for lead in await db.scalars(
            select(Lead).join(Pipeline, Pipeline.id == Lead.pipeline_id).join(LeadStage, LeadStage.id == Lead.stage_id)
            .where(Lead.student_id == s.id, Pipeline.code == "return", Lead.archived_at.is_(None),
                   LeadStage.is_won.is_(False), LeadStage.is_lost.is_(False))):
        lead.archived_at = now()
        db.add(LeadEvent(lead_id=lead.id, at=now(), kind="note", text=why, actor_id=actor_id, meta={}))


async def left_to_funnel(db: AsyncSession, commit: bool) -> dict:
    """One-off: every student who is «ушёл» today and has no open card in «Возврат» gets one on «Ушёл»."""
    from app.models.learning import StudentStatus
    from app.models import Branch, Lead

    out = {"left": 0, "new": 0, "had_card": 0, "by_branch": {}, "no_manager": 0, "lines": []}
    for s in list(await db.scalars(select(Student).where(Student.status == StudentStatus.LEFT, Student.archived_at.is_(None))
                                   .order_by(Student.branch_id, Student.full_name))):
        out["left"] += 1
        before = await db.scalar(select(func.max(Lead.id))) or 0
        stage = "left" if not s.return_note else "contacted"
        why = "Ушёл" + (f" {local(s.left_at):%d.%m.%Y}" if s.left_at else "") + (f". Причина: {s.leave_reason}" if s.leave_reason else "") \
            + (f". Возврат: {s.return_note}" if s.return_note else "")
        lead = await return_card(db, s, None, stage, why)
        if lead is None or lead.id <= before:
            out["had_card"] += 1
            continue
        out["new"] += 1
        b = await db.scalar(select(Branch.name).where(Branch.id == s.branch_id))
        out["by_branch"][b] = out["by_branch"].get(b, 0) + 1
        who = await db.scalar(select(User.full_name).where(User.id == lead.assignee_id)) if lead.assignee_id else None
        out["no_manager"] += who is None
        out["lines"].append(f"{b}: {s.full_name} — {why} — {who or 'общий'}")
    if commit:
        await db.commit()
    else:
        await db.rollback()
    out["applied"] = commit
    return out
