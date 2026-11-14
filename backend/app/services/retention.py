"""Keeping students: follow-up tasks for the methodist (two absences in a row, a student who wants to leave)."""

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Role, Student, Task, TaskAssignee, User, UserBranch
from app.models.identity import UserRole
from app.models.work import TaskStatus
from app.services.clock import now
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
                    creator_id: int, hours: int = 24) -> Task | None:
    """One open task of a kind per student: a second trigger does not make a duplicate."""
    if await open_task(db, s.id, auto_kind):
        return None
    who = await methodists(db, s.branch_id)
    if not who:
        return None
    t = Task(title=title[:255], description=description, creator_id=creator_id, branch_id=s.branch_id, priority="high",
             due_at=now() + timedelta(hours=hours), status=TaskStatus.NEW, link_type="student", link_id=s.id,
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
