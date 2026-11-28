"""Tasks on leads, as in Bitrix: every open lead has a next task; the manager sets it for himself and works by it daily."""
from datetime import datetime, timedelta

from fastapi import APIRouter
from pydantic import Field
from sqlalchemy import func, select

from app.core.deps import DB, Actor, require
from app.core.errors import bad_request, forbidden, not_found
from app.core.permissions import OWN
from app.core.query import icontains
from app.core.schemas import In
from app.models import Lead, LeadEvent, LeadStage, Task, TaskAssignee, User
from app.models.work import TaskStatus
from app.modules.crm.service import get_lead_scoped, lead_filter
from app.services import crm as crm_svc
from app.services.clock import at_local, local, now, today

router = APIRouter(prefix="/crm", tags=["crm"])
OPEN = Task.status.not_in((TaskStatus.DONE, TaskStatus.CANCELLED))
LEAD_TASK = (Task.link_type == "lead") & Task.archived_at.is_(None)


class TaskIn(In):
    title: str = Field(min_length=1, max_length=255)
    due_at: datetime
    daily: bool = False


class TaskPatch(In):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    due_at: datetime | None = None
    daily: bool | None = None


class DoneIn(In):
    result: str | None = Field(default=None, max_length=1000)
    next: TaskIn | None = None


def _closed(st: LeadStage | None) -> bool:
    return bool(st and (st.is_won or st.is_lost))


async def _make(db: DB, lead: Lead, actor_id: int, title: str, due_at: datetime, daily: bool) -> Task:
    t = Task(title=title.strip(), creator_id=actor_id, branch_id=lead.branch_id, due_at=due_at, status=TaskStatus.NEW,
             link_type="lead", link_id=lead.id, recurrence="daily" if daily else None)
    db.add(t)
    await db.flush()
    db.add(TaskAssignee(task_id=t.id, user_id=actor_id))
    return t


async def _sync(db: DB, lead: Lead) -> None:
    lead.next_action_at = await db.scalar(select(func.min(Task.due_at)).where(LEAD_TASK, Task.link_id == lead.id, OPEN))


async def _rows(db: DB, tasks: list[Task]) -> list[dict]:
    if not tasks:
        return []
    leads = {x.id: x for x in await db.scalars(select(Lead).where(Lead.id.in_({t.link_id for t in tasks})))}
    stages = {s.id: s for s in await db.scalars(select(LeadStage))}
    who = dict((await db.execute(select(TaskAssignee.task_id, User.full_name).join(User, User.id == TaskAssignee.user_id)
                                 .where(TaskAssignee.task_id.in_([t.id for t in tasks])))).all())
    ids = dict((await db.execute(select(TaskAssignee.task_id, TaskAssignee.user_id)
                                 .where(TaskAssignee.task_id.in_([t.id for t in tasks])))).all())
    out = []
    for t in tasks:
        lead = leads.get(t.link_id)
        if lead is None:
            continue
        st = stages.get(lead.stage_id)
        out.append({"id": t.id, "title": t.title, "due_at": t.due_at, "daily": t.recurrence == "daily", "done": t.status == TaskStatus.DONE,
                    "done_at": t.done_at, "assignee_id": ids.get(t.id), "assignee_name": who.get(t.id),
                    "lead": {"id": lead.id, "full_name": lead.full_name, "stage_name": st.name if st else None,
                             "stage_color": st.color if st else None}})
    return out


def _wide(actor: Actor) -> bool:
    return actor.scope("crm", "view") != OWN


@router.get("/tasks")
async def lead_tasks(db: DB, actor: Actor = require("crm", "view"), box: str = "mine", branch_id: int | None = None,
                     user_id: int | None = None, q: str | None = None) -> dict:
    """Open tasks on leads, what was done today, and the open leads that still have no task."""
    mine = box != "all" or not _wide(actor)
    visible = select(Lead.id).where(Lead.archived_at.is_(None), lead_filter(actor))
    if branch_id:
        visible = visible.where((Lead.branch_id == branch_id) | Lead.branch_id.is_(None))
    if q:
        visible = visible.where(icontains(Lead.full_name, q))
    base = select(Task).where(LEAD_TASK, Task.link_id.in_(visible))
    uid = actor.id if mine else user_id
    if uid:
        base = base.where(Task.id.in_(select(TaskAssignee.task_id).where(TaskAssignee.user_id == uid)))
    start = at_local(today(), datetime.min.time())
    tasks = list(await db.scalars(base.where(OPEN).order_by(Task.due_at).limit(500)))
    done = list(await db.scalars(base.where(Task.status == TaskStatus.DONE, Task.done_at >= start).order_by(Task.done_at.desc()).limit(100)))
    has_task = select(Task.id).where(LEAD_TASK, Task.link_id == Lead.id, OPEN).exists()
    bare = select(Lead).join(LeadStage, LeadStage.id == Lead.stage_id).where(
        Lead.id.in_(visible), LeadStage.is_won.is_(False), LeadStage.is_lost.is_(False), ~has_task)
    if uid:
        bare = bare.where((Lead.assignee_id == uid) | (Lead.owner_id == uid) | (Lead.assignee_id.is_(None) & Lead.owner_id.is_(None)))
    stages = {s.id: s for s in await db.scalars(select(LeadStage))}
    no_total = await db.scalar(select(func.count()).select_from(bare.subquery()))
    no_task = [{"id": x.id, "full_name": x.full_name, "stage_name": stages[x.stage_id].name if x.stage_id in stages else None,
                "stage_color": stages[x.stage_id].color if x.stage_id in stages else None}
               for x in await db.scalars(bare.order_by(Lead.stage_changed_at.desc()).limit(100))]
    people = []
    if _wide(actor):
        people = [{"id": i, "full_name": n} for i, n in (await db.execute(
            select(User.id, User.full_name).where(User.id.in_(
                select(TaskAssignee.user_id).join(Task, Task.id == TaskAssignee.task_id).where(LEAD_TASK, Task.link_id.in_(visible), OPEN)))
            .order_by(User.full_name))).all()]
    return {"tasks": await _rows(db, tasks), "done": await _rows(db, done), "no_task": no_task, "no_task_total": no_total,
            "wide": _wide(actor), "people": people}


@router.get("/leads/{lead_id}/tasks")
async def tasks_of_lead(lead_id: int, db: DB, actor: Actor = require("crm", "view")) -> list[dict]:
    lead = await get_lead_scoped(db, actor, lead_id)
    return await _rows(db, list(await db.scalars(select(Task).where(LEAD_TASK, Task.link_id == lead.id, OPEN).order_by(Task.due_at))))


@router.post("/leads/{lead_id}/tasks", status_code=201)
async def add_task(lead_id: int, body: TaskIn, db: DB, actor: Actor = require("crm", "edit")) -> dict:
    """The manager sets the task for himself."""
    lead = await get_lead_scoped(db, actor, lead_id, "edit")
    t = await _make(db, lead, actor.id, body.title, body.due_at, body.daily)
    db.add(LeadEvent(lead_id=lead.id, at=now(), kind="note", actor_id=actor.id, meta={"task_id": t.id},
                     text=f"Задача на {local(body.due_at):%d.%m %H:%M}: {t.title}" + (" (каждый день)" if body.daily else "")))
    await _sync(db, lead)
    await db.commit()
    return (await _rows(db, [t]))[0]


async def _mine(db: DB, actor: Actor, task_id: int) -> tuple[Task, Lead]:
    t = await db.scalar(select(Task).where(Task.id == task_id, LEAD_TASK))
    lead = await db.scalar(select(Lead).where(Lead.id == t.link_id, lead_filter(actor))) if t else None
    if t is None or lead is None:
        raise not_found("Задача")
    own = await db.scalar(select(TaskAssignee.id).where(TaskAssignee.task_id == t.id, TaskAssignee.user_id == actor.id))
    if not own and not _wide(actor):
        raise forbidden("Это задача другого менеджера")
    return t, lead


@router.patch("/tasks/{task_id}")
async def change_task(task_id: int, body: TaskPatch, db: DB, actor: Actor = require("crm", "edit")) -> dict:
    t, lead = await _mine(db, actor, task_id)
    if t.status in (TaskStatus.DONE, TaskStatus.CANCELLED):
        raise bad_request("Задача уже закрыта")
    if body.title is not None:
        t.title = body.title.strip()
    if body.due_at is not None:
        t.due_at = body.due_at
    if body.daily is not None:
        t.recurrence = "daily" if body.daily else None
    await _sync(db, lead)
    await db.commit()
    return (await _rows(db, [t]))[0]


@router.post("/tasks/{task_id}/done")
async def finish_task(task_id: int, body: DoneIn, db: DB, actor: Actor = require("crm", "edit")) -> dict:
    """Closing a task of an open lead leaves the lead with a next one: tomorrow's copy of a daily task, or the one given here."""
    t, lead = await _mine(db, actor, task_id)
    if t.status in (TaskStatus.DONE, TaskStatus.CANCELLED):
        raise bad_request("Задача уже закрыта")
    st = await db.get(LeadStage, lead.stage_id)
    live = lead.archived_at is None and not _closed(st)
    others = await db.scalar(select(func.count()).select_from(Task).where(LEAD_TASK, Task.link_id == lead.id, OPEN, Task.id != t.id))
    nxt = None
    if body.next is not None:
        nxt = await _make(db, lead, actor.id, body.next.title, body.next.due_at, body.next.daily)
    elif live and t.recurrence == "daily":
        day = max(today(), local(t.due_at).date() if t.due_at else today()) + timedelta(days=1)
        nxt = await _make(db, lead, actor.id, t.title, at_local(day, local(t.due_at or now()).time()), True)
    elif live and not others:
        raise bad_request("Поставьте следующую задачу по лиду")
    t.status, t.done_at = TaskStatus.DONE, now()
    lead.last_activity_at = now()
    db.add(LeadEvent(lead_id=lead.id, at=now(), kind="note", actor_id=actor.id, meta={"task_id": t.id, "task_done": True},
                     text=f"Задача выполнена: {t.title}" + (f". {body.result.strip()}" if body.result and body.result.strip() else "")))
    await crm_svc.worked(db, lead, actor.id)
    await _sync(db, lead)
    await db.commit()
    return {"done": (await _rows(db, [t]))[0], "next": (await _rows(db, [nxt]))[0] if nxt else None}
