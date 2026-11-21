"""Tasks between staff (ТЗ 11), with comments, review step and recurring templates."""

from datetime import datetime

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import exists, func, or_, select

from app.core.audit import write_audit
from app.core.deps import DB, Actor, require
from app.core.errors import bad_request, forbidden, not_found
from app.core.permissions import OWN
from app.core.query import paginate
from app.core.schemas import In, Page
from app.models import Task, TaskAssignee, TaskComment, User, UserBranch
from app.models.work import TaskStatus
from app.services.clock import now
from app.services.messaging import notify_user

router = APIRouter(tags=["tasks"])


class TaskIn(In):
    title: str = Field(min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=8000)
    branch_id: int | None = None
    priority: str = Field(default="normal", pattern="^(low|normal|high)$")
    due_at: datetime | None = None
    assignee_ids: list[int] = Field(min_length=1, max_length=50)
    link_type: str | None = Field(default=None, pattern="^(student|lead|group|lesson)$")
    link_id: int | None = None
    recurrence: str | None = Field(default=None, pattern="^(daily|weekly)$")


class TaskPatch(In):
    title: str | None = Field(default=None, min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=8000)
    priority: str | None = Field(default=None, pattern="^(low|normal|high)$")
    due_at: datetime | None = None
    status: str | None = Field(default=None, max_length=255)
    assignee_ids: list[int] | None = Field(default=None, min_length=1, max_length=50)


class TaskOut(BaseModel):
    id: int
    title: str
    description: str | None
    creator_id: int
    creator_name: str | None
    branch_id: int | None
    priority: str
    due_at: datetime | None
    status: str
    done_at: datetime | None
    overdue: bool
    link_type: str | None
    link_id: int | None
    link_title: str | None = None
    recurrence: str | None
    assignees: list[dict]
    comments: int = 0
    created_at: datetime


async def _link_title(db: DB, kind: str | None, ref: int | None) -> str | None:
    from app.models import Group, Lead, Lesson, Student
    from app.services.clock import local

    if not kind or not ref:
        return None
    if kind == "student":
        return await db.scalar(select(Student.full_name).where(Student.id == ref))
    if kind == "lead":
        return await db.scalar(select(Lead.full_name).where(Lead.id == ref))
    if kind == "group":
        return await db.scalar(select(Group.name).where(Group.id == ref))
    if kind == "lesson":
        row = (await db.execute(select(Lesson.starts_at, Group.name).outerjoin(Group, Group.id == Lesson.group_id)
                                .where(Lesson.id == ref))).first()
        return f"{row[1] or 'Урок'} {local(row[0]).strftime('%d.%m %H:%M')}" if row else None
    return None


async def _out(db: DB, t: Task) -> TaskOut:
    rows = (await db.execute(select(User.id, User.full_name).join(TaskAssignee, TaskAssignee.user_id == User.id)
                             .where(TaskAssignee.task_id == t.id))).all()
    creator = await db.get(User, t.creator_id)
    n = await db.scalar(select(func.count()).select_from(TaskComment).where(TaskComment.task_id == t.id))
    link_title = await _link_title(db, t.link_type, t.link_id)
    return TaskOut(id=t.id, title=t.title, description=t.description, creator_id=t.creator_id,
                   creator_name=creator.full_name if creator else None, branch_id=t.branch_id, priority=t.priority,
                   due_at=t.due_at, status=t.status, done_at=t.done_at,
                   overdue=bool(t.due_at and t.due_at < now() and t.status not in (TaskStatus.DONE, TaskStatus.CANCELLED)),
                   link_type=t.link_type, link_id=t.link_id, link_title=link_title, recurrence=t.recurrence,
                   assignees=[{"id": i, "full_name": n_} for i, n_ in rows], comments=n or 0, created_at=t.created_at)


def _is_assignee(user_id: int):
    return exists().where(TaskAssignee.task_id == Task.id, TaskAssignee.user_id == user_id)


def _visible(actor: Actor):
    """Everyone sees tasks they created or got; branch/network scope also sees the branch's tasks."""
    mine = or_(Task.creator_id == actor.id, _is_assignee(actor.id))
    s = actor.scope("tasks", "view")
    if s == OWN:
        return mine
    allowed = actor.branches_for("tasks", "view")
    return or_(mine, Task.branch_id.in_(allowed)) if allowed is not None else True


async def _get(db: DB, actor: Actor, task_id: int) -> Task:
    t = await db.scalar(select(Task).where(Task.id == task_id, Task.archived_at.is_(None), _visible(actor)))
    if t is None:
        raise not_found("Задача")
    return t


async def _check_assignees(db: DB, actor: Actor, ids: list[int]) -> None:
    allowed = actor.branches_for("tasks", "create")
    users = list(await db.scalars(select(User).where(User.id.in_(ids), User.kind == "staff", User.is_active.is_(True),
                                                     User.archived_at.is_(None))))
    if len(users) != len(set(ids)):
        raise bad_request("Исполнитель не найден")
    if allowed is not None:
        ok = set(await db.scalars(select(UserBranch.user_id).where(UserBranch.user_id.in_(ids), UserBranch.branch_id.in_(allowed))))
        if set(ids) - ok - {actor.id}:
            raise forbidden("Исполнитель из другого филиала")


@router.get("/tasks", response_model=Page[TaskOut])
async def list_tasks(db: DB, actor: Actor = require("tasks", "view"), box: str = "mine", status: str | None = None,
                     overdue: bool = False, branch_id: int | None = None, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)) -> Page:
    q = select(Task).where(Task.archived_at.is_(None), _visible(actor))
    if box == "mine":
        q = q.where(_is_assignee(actor.id))
    elif box == "created":
        q = q.where(Task.creator_id == actor.id)
    if status:
        q = q.where(Task.status == status)
    elif box != "all":
        q = q.where(Task.status.not_in((TaskStatus.DONE, TaskStatus.CANCELLED)))
    if overdue:
        q = q.where(Task.due_at < now(), Task.status.not_in((TaskStatus.DONE, TaskStatus.CANCELLED)))
    if branch_id:
        q = q.where(Task.branch_id == branch_id)
    rows, total = await paginate(db, q.order_by(Task.due_at.asc().nulls_last(), Task.id.desc()), limit, offset)
    return Page(items=[await _out(db, t) for t in rows], total=total, limit=limit, offset=offset)


@router.post("/tasks", response_model=TaskOut, status_code=201)
async def create_task(body: TaskIn, db: DB, actor: Actor = require("tasks", "create")) -> TaskOut:
    if body.branch_id is not None:
        actor.ensure_branch("tasks", "create", body.branch_id)
    await _check_assignees(db, actor, body.assignee_ids)
    data = body.model_dump(exclude={"assignee_ids"})
    t = Task(**data, creator_id=actor.id, status=TaskStatus.NEW)
    db.add(t)
    await db.flush()
    for uid in set(body.assignee_ids):
        db.add(TaskAssignee(task_id=t.id, user_id=uid))
        if uid != actor.id:
            await notify_user(db, uid, "task", f"Новая задача: {t.title}", body=f"от {actor.user.full_name}", link=f"/tasks/{t.id}")
    await write_audit(db, actor_id=actor.id, action="task.create", entity="task", entity_id=t.id, branch_id=t.branch_id,
                      ip=actor.ip, after={"title": t.title, "assignees": sorted(set(body.assignee_ids))})
    await db.commit()
    return await _out(db, t)


@router.get("/tasks/{task_id}", response_model=TaskOut)
async def get_task(task_id: int, db: DB, actor: Actor = require("tasks", "view")) -> TaskOut:
    return await _out(db, await _get(db, actor, task_id))


# Assignee moves new → in_progress → review/done; only the creator closes after review or cancels.
ASSIGNEE_MOVES = {TaskStatus.NEW: {TaskStatus.IN_PROGRESS, TaskStatus.REVIEW, TaskStatus.DONE},
                  TaskStatus.IN_PROGRESS: {TaskStatus.REVIEW, TaskStatus.DONE},
                  TaskStatus.REVIEW: {TaskStatus.IN_PROGRESS}}


@router.patch("/tasks/{task_id}", response_model=TaskOut)
async def update_task(task_id: int, body: TaskPatch, db: DB, actor: Actor = require("tasks", "view")) -> TaskOut:
    t = await _get(db, actor, task_id)
    is_creator = t.creator_id == actor.id or (actor.can("tasks", "create") and actor.scope("tasks", "create") != OWN
                                              and (actor.branches_for("tasks", "create") is None
                                                   or t.branch_id in actor.branches_for("tasks", "create")))
    is_assignee = await db.scalar(select(TaskAssignee).where(TaskAssignee.task_id == t.id, TaskAssignee.user_id == actor.id))
    fields = body.model_dump(exclude_unset=True)
    edits = {k: v for k, v in fields.items() if k not in ("status",)}
    if edits and not is_creator:
        raise forbidden("Менять задачу может её автор")
    before = {"status": t.status, "title": t.title}
    if "assignee_ids" in edits:
        await _check_assignees(db, actor, body.assignee_ids)
        old = set(await db.scalars(select(TaskAssignee.user_id).where(TaskAssignee.task_id == t.id)))
        for a in await db.scalars(select(TaskAssignee).where(TaskAssignee.task_id == t.id)):
            if a.user_id not in body.assignee_ids:
                await db.delete(a)
        for uid in set(body.assignee_ids) - old:
            db.add(TaskAssignee(task_id=t.id, user_id=uid))
            await notify_user(db, uid, "task", f"Новая задача: {t.title}", link=f"/tasks/{t.id}")
        edits.pop("assignee_ids")
    for k, v in edits.items():
        setattr(t, k, v)
    if body.status and body.status != t.status:
        if body.status not in TaskStatus.ALL:
            raise bad_request("Неизвестный статус")
        if not is_creator and not (is_assignee and body.status in ASSIGNEE_MOVES.get(t.status, set())):
            raise forbidden("Этот статус ставит автор задачи")
        t.status = body.status
        t.done_at = now() if body.status == TaskStatus.DONE else None
        if body.status in (TaskStatus.REVIEW, TaskStatus.DONE) and t.creator_id != actor.id:
            await notify_user(db, t.creator_id, "task", f"{'На проверке' if body.status == TaskStatus.REVIEW else 'Выполнено'}: {t.title}",
                              body=actor.user.full_name, link=f"/tasks/{t.id}")
    await write_audit(db, actor_id=actor.id, action="task.update", entity="task", entity_id=t.id, branch_id=t.branch_id,
                      ip=actor.ip, before=before, after=body.model_dump(mode="json", exclude_unset=True))
    await db.commit()
    return await _out(db, t)


class CommentIn(In):
    text: str = Field(min_length=1, max_length=4000)
    file_url: str | None = Field(default=None, max_length=255)


@router.get("/tasks/{task_id}/comments")
async def comments(task_id: int, db: DB, actor: Actor = require("tasks", "view")) -> list[dict]:
    t = await _get(db, actor, task_id)
    rows = (await db.execute(select(TaskComment, User.full_name).join(User, User.id == TaskComment.author_id)
                             .where(TaskComment.task_id == t.id).order_by(TaskComment.id))).all()
    return [{"id": c.id, "author_id": c.author_id, "author": n, "at": c.at, "text": c.text, "file_url": c.file_url} for c, n in rows]


@router.post("/tasks/{task_id}/comments", status_code=201)
async def add_comment(task_id: int, body: CommentIn, db: DB, actor: Actor = require("tasks", "view")) -> dict:
    t = await _get(db, actor, task_id)
    c = TaskComment(task_id=t.id, author_id=actor.id, at=now(), text=body.text, file_url=body.file_url)
    db.add(c)
    await db.flush()
    people = set(await db.scalars(select(TaskAssignee.user_id).where(TaskAssignee.task_id == t.id))) | {t.creator_id}
    for uid in people - {actor.id}:
        await notify_user(db, uid, "task", f"Комментарий: {t.title}", body=body.text[:140], link=f"/tasks/{t.id}")
    await db.commit()
    return {"id": c.id, "at": c.at}


@router.post("/tasks/{task_id}/archive", status_code=204)
async def archive_task(task_id: int, db: DB, actor: Actor = require("tasks", "create")) -> None:
    t = await _get(db, actor, task_id)
    if t.creator_id != actor.id and not actor.is_owner:
        raise forbidden("Удалить задачу может её автор")
    t.archived_at = now()
    await write_audit(db, actor_id=actor.id, action="task.archive", entity="task", entity_id=t.id, branch_id=t.branch_id, ip=actor.ip)
    await db.commit()
