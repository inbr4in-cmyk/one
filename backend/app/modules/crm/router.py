from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.query import icontains
from app.core.audit import diff, snapshot, write_audit
from app.core.deps import DB, Actor, require, require_staff
from app.core.errors import bad_request, conflict, forbidden, not_found
from app.core.permissions import NETWORK
from app.core.schemas import In, ORM
from app.core.security import mask_phone, normalize_phone
from app.models import (
    Attempt, Conversation, ExternalContact, GroupMember, Lead, LeadEvent, LeadStage, LeadStageAccess, Lesson, Pipeline, Room,
    Student, User, UserBranch,
)
from app.models.identity import Role, RolePermission, UserKind, UserRole
from app.models.crm import LeadSource
from app.models.learning import LessonStatus, StudentStatus
from app.modules.crm.service import (
    create_lead, find_by_phone, find_client_by_phone, get_lead_scoped, lead_filter, merge_into_student,
    set_branch, stage_editable,
)
from app.modules.students.scope import get_student_scoped
from app.modules.students.router import add_guardian, upsert_portal_user
from app.modules.students.schemas import GuardianIn
from app.services import crm as crm_svc
from app.services.clock import at_local, local, local_range, now, today
from app.services.messaging import send_whatsapp_text
from app.services.values import setting

router = APIRouter(prefix="/crm", tags=["crm"])
BACKDATE_DAYS = 31  # how far back a lead may be dated when it is entered later


class StageOut(ORM):
    id: int
    code: str
    name: str
    color: str
    order: int
    is_won: bool
    is_lost: bool
    stale_after_hours: int | None = None
    # Built-in stages drive automation (trial booked, paid...): they can be renamed and recoloured, not removed.
    system: bool = False


class PipelineOut(ORM):
    id: int
    code: str
    name: str
    stages: list[StageOut] = []


class LeadIn(In):
    full_name: str = Field(min_length=2, max_length=255)
    phone: str | None = Field(default=None, max_length=32)
    branch_id: int
    source: str = LeadSource.SALES
    age: int | None = Field(default=None, ge=2, le=99)
    parent_name: str | None = Field(default=None, max_length=255)
    parent_phone: str | None = Field(default=None, max_length=32)
    level_id: int | None = None
    notes: str | None = Field(default=None, max_length=4000)
    next_action_at: datetime | None = None
    assignee_id: int | None = None
    contacted_on: date | None = None  # the day the person got in touch, if the card is entered later


class LeadPatch(In):
    full_name: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=32)
    age: int | None = None
    parent_name: str | None = Field(default=None, max_length=255)
    parent_phone: str | None = Field(default=None, max_length=32)
    level_id: int | None = None
    notes: str | None = Field(default=None, max_length=4000)
    next_action_at: datetime | None = None
    assignee_id: int | None = None
    is_hot: bool | None = None
    branch_id: int | None = None


PATCH_TITLES = {"full_name": "имя", "phone": "телефон", "age": "возраст", "parent_name": "родитель",
                "parent_phone": "телефон родителя", "level_id": "уровень", "notes": "заметка", "next_action_at": "следующий шаг"}


class LeadCard(BaseModel):
    id: int
    full_name: str
    phone: str | None
    age: int | None
    parent_name: str | None
    parent_phone: str | None
    branch_id: int | None
    pipeline_id: int
    stage_id: int
    stage_changed_at: datetime
    source: str
    owner_id: int | None
    owner_name: str | None = None
    assignee_id: int | None
    student_id: int | None
    level_id: int | None
    placement_score: int | None
    trial_lesson_id: int | None
    trial_at: datetime | None = None
    lost_reason: str | None
    next_action_at: datetime | None
    last_activity_at: datetime | None
    notes: str | None
    is_hot: bool
    created_at: datetime
    stale: bool = False
    waiting_min: int | None = None
    channel: str | None = None
    conversation_id: int | None = None
    existing_student: dict | None = None  # a student (or a student's parent) already has this phone
    can_edit: bool = True  # False: the admin left this funnel stage to me for viewing only
    assignee_name: str | None = None


class EventOut(ORM):
    id: int
    at: datetime
    kind: str
    text: str | None
    actor_id: int | None
    actor_name: str | None = None
    meta: dict


async def _card(db: DB, actor: Actor, lead: Lead) -> LeadCard:
    """One card, with a hint when the lead's phone already belongs to a student of the school."""
    c = (await _cards(db, actor, [lead]))[0]
    if lead.student_id is None and lead.archived_at is None:
        s = await find_client_by_phone(db, lead.phone) or await find_client_by_phone(db, lead.parent_phone)
        if s:
            c.existing_student = {"id": s.id, "full_name": s.full_name}
    return c


def _phone(actor: Actor, phone: str | None) -> str | None:
    return phone if actor.can("students", "view_contacts") or actor.can("crm", "edit") else mask_phone(phone)


async def _cards(db: DB, actor: Actor, leads: list[Lead]) -> list[LeadCard]:
    if not leads:
        return []
    stages = {s.id: s for s in await db.scalars(select(LeadStage))}
    owners = dict((await db.execute(select(User.id, User.full_name).where(
        User.id.in_({x.owner_id for x in leads if x.owner_id} | {x.assignee_id for x in leads if x.assignee_id})))).all())
    conv_rows = (await db.execute(
        select(Conversation.id, Conversation.channel, Conversation.last_inbound_at, Conversation.unread, ExternalContact.lead_id)
        .join(ExternalContact, ExternalContact.id == Conversation.contact_id)
        .where(ExternalContact.lead_id.in_([x.id for x in leads]))
    )).all()
    by_lead = {r[4]: r for r in conv_rows}
    trial_at = dict((await db.execute(select(Lesson.id, Lesson.starts_at).where(
        Lesson.id.in_({x.trial_lesson_id for x in leads if x.trial_lesson_id})))).all())
    warn_min = int(await setting(db, "lead_first_reply_warn_min") or 30)
    out = []
    t = now()
    for x in leads:
        st = stages.get(x.stage_id)
        c = LeadCard(**{k: getattr(x, k) for k in LeadCard.model_fields if hasattr(x, k)})
        c.phone, c.parent_phone = _phone(actor, x.phone), _phone(actor, x.parent_phone)
        c.owner_name = owners.get(x.owner_id)
        c.assignee_name = owners.get(x.assignee_id)
        c.can_edit = stage_editable(actor, x.stage_id)
        c.trial_at = trial_at.get(x.trial_lesson_id)
        conv = by_lead.get(x.id)
        if conv:
            c.conversation_id, c.channel = conv[0], conv[1]
            if conv[3] and conv[2]:
                c.waiting_min = int((t - conv[2]).total_seconds() // 60)
        elif st and st.code == "new":
            c.waiting_min = int((t - x.created_at).total_seconds() // 60)
        stale_h = st.stale_after_hours if st else None
        c.stale = bool((c.waiting_min is not None and c.waiting_min >= warn_min) or
                       (stale_h and not (st.is_won or st.is_lost) and (t - x.stage_changed_at) > timedelta(hours=stale_h)))
        out.append(c)
    return out


@router.get("/pipelines", response_model=list[PipelineOut])
async def pipelines(db: DB, actor: Actor = require("crm", "view")) -> list[PipelineOut]:
    out = []
    for p in await db.scalars(select(Pipeline).where(Pipeline.archived_at.is_(None)).order_by(Pipeline.id)):
        o = PipelineOut.model_validate(p)
        o.stages = [_stage_out(s) for s in await db.scalars(
            select(LeadStage).where(LeadStage.pipeline_id == p.id, LeadStage.archived_at.is_(None)).order_by(LeadStage.order))]
        out.append(o)
    return out


SYSTEM_STAGES = {"new", "contacted", "trial_booked", "trial_done", "paid", "lost", "left"}


def _stage_out(st: LeadStage) -> StageOut:
    o = StageOut.model_validate(st)
    o.system = st.code in SYSTEM_STAGES or st.is_won or st.is_lost
    return o


class StageIn(In):
    name: str = Field(min_length=1, max_length=120)
    color: str = Field(default="#5B6782", pattern=r"^#[0-9A-Fa-f]{6}$")
    stale_after_hours: int | None = Field(default=None, ge=1, le=24 * 365)


@router.post("/pipelines/{pipeline_id}/stages", response_model=StageOut, status_code=201)
async def add_stage(pipeline_id: int, body: StageIn, db: DB, actor: Actor = require("settings", "edit")) -> StageOut:
    """A new column goes before the final ones (won / lost)."""
    p = await db.get(Pipeline, pipeline_id)
    if p is None or p.archived_at is not None:
        raise not_found("Воронка")
    stages = list(await db.scalars(select(LeadStage).where(LeadStage.pipeline_id == p.id, LeadStage.archived_at.is_(None))
                                   .order_by(LeadStage.order)))
    pos = next((i for i, x in enumerate(stages) if x.is_won or x.is_lost), len(stages))
    n = await db.scalar(select(func.count()).select_from(LeadStage).where(LeadStage.pipeline_id == p.id))
    st = LeadStage(pipeline_id=p.id, name=body.name.strip(), code=f"custom_{p.id}_{n + 1}", color=body.color,
                   stale_after_hours=body.stale_after_hours, order=pos)
    stages.insert(pos, st)
    db.add(st)
    for i, x in enumerate(stages):
        x.order = i
    await db.flush()
    await write_audit(db, actor_id=actor.id, action="lead_stage.create", entity="lead_stage", entity_id=st.id, ip=actor.ip,
                      after={"name": st.name, "pipeline": p.code})
    await db.commit()
    return _stage_out(st)


@router.patch("/stages/{stage_id}", response_model=StageOut)
async def edit_stage(stage_id: int, body: StageIn, db: DB, actor: Actor = require("settings", "edit")) -> StageOut:
    st = await db.get(LeadStage, stage_id)
    if st is None or st.archived_at is not None:
        raise not_found("Этап")
    before = snapshot(st, ["name", "color", "stale_after_hours"])
    st.name, st.color, st.stale_after_hours = body.name.strip(), body.color, body.stale_after_hours
    b, a = diff(before, snapshot(st, list(before)))
    await write_audit(db, actor_id=actor.id, action="lead_stage.update", entity="lead_stage", entity_id=st.id, ip=actor.ip,
                      before=b, after=a)
    await db.commit()
    return _stage_out(st)


class StageOrderIn(In):
    stage_ids: list[int] = Field(min_length=1, max_length=50)


@router.put("/pipelines/{pipeline_id}/order", response_model=list[StageOut])
async def order_stages(pipeline_id: int, body: StageOrderIn, db: DB, actor: Actor = require("settings", "edit")) -> list[StageOut]:
    """New column order. Final stages (won / lost) always stay at the end."""
    stages = {x.id: x for x in await db.scalars(select(LeadStage).where(LeadStage.pipeline_id == pipeline_id,
                                                                         LeadStage.archived_at.is_(None)))}
    if set(body.stage_ids) != set(stages) or len(body.stage_ids) != len(stages):
        raise bad_request("Список этапов не совпадает — обновите страницу")
    ordered = [stages[i] for i in body.stage_ids]
    ordered = [x for x in ordered if not (x.is_won or x.is_lost)] + [x for x in ordered if x.is_won or x.is_lost]
    for i, x in enumerate(ordered):
        x.order = i
    await write_audit(db, actor_id=actor.id, action="lead_stage.order", entity="pipeline", entity_id=pipeline_id, ip=actor.ip,
                      after={"order": [x.name for x in ordered]})
    await db.commit()
    return [_stage_out(x) for x in ordered]


@router.post("/stages/{stage_id}/archive", status_code=204)
async def archive_stage(stage_id: int, db: DB, actor: Actor = require("settings", "edit")) -> None:
    st = await db.get(LeadStage, stage_id)
    if st is None or st.archived_at is not None:
        raise not_found("Этап")
    if _stage_out(st).system:
        raise bad_request("Это встроенный этап, на нём работает автоматика. Его можно переименовать, но не убрать")
    if await db.scalar(select(Lead.id).where(Lead.stage_id == st.id, Lead.archived_at.is_(None)).limit(1)):
        raise bad_request("В этом этапе есть лиды — сначала перенесите их в другой этап")
    st.archived_at = now()
    await write_audit(db, actor_id=actor.id, action="lead_stage.archive", entity="lead_stage", entity_id=st.id, ip=actor.ip,
                      before={"name": st.name})
    await db.commit()


@router.get("/board")
async def board(db: DB, actor: Actor = require("crm", "view"), pipeline: str = "main", branch_id: int | None = None,
                source: str | None = None, owner_id: int | None = None, q: str | None = None) -> dict:
    p = await db.scalar(select(Pipeline).where(Pipeline.code == pipeline))
    if p is None:
        raise not_found("Воронка")
    stmt = select(Lead).where(Lead.pipeline_id == p.id, Lead.archived_at.is_(None), lead_filter(actor))
    if branch_id:
        stmt = stmt.where((Lead.branch_id == branch_id) | Lead.branch_id.is_(None))
    if source:
        stmt = stmt.where(Lead.source == source)
    if owner_id:
        stmt = stmt.where(Lead.owner_id == owner_id)
    if q:
        stmt = stmt.where(icontains(Lead.full_name, q))
    # Closed columns only show the last 30 days.
    stages = list(await db.scalars(select(LeadStage).where(LeadStage.pipeline_id == p.id, LeadStage.archived_at.is_(None))
                                   .order_by(LeadStage.order)))
    cols = []
    for st in stages:
        if st.id in actor.stage_hidden:
            continue
        s2 = stmt.where(Lead.stage_id == st.id)
        if st.is_won or st.is_lost:
            s2 = s2.where(Lead.stage_changed_at >= now() - timedelta(days=30))
        total = await db.scalar(select(func.count()).select_from(s2.subquery()))
        leads = list(await db.scalars(s2.order_by(Lead.is_hot.desc(), Lead.stage_changed_at.desc()).limit(100)))
        cols.append({"stage": StageOut.model_validate(st).model_dump(), "total": total,
                     "leads": [c.model_dump() for c in await _cards(db, actor, leads)]})
    return {"pipeline": {"id": p.id, "code": p.code, "name": p.name}, "columns": cols}


@router.post("/leads", response_model=LeadCard, status_code=201)
async def new_lead(body: LeadIn, db: DB, actor: Actor = require("crm", "create")) -> LeadCard:
    actor.ensure_branch("crm", "create", body.branch_id)
    if not await valid_source(db, body.source):
        raise bad_request("Неизвестный источник")
    phone = normalize_phone(body.phone) if body.phone else None
    if dup := await find_by_phone(db, phone):
        raise conflict(f"Лид с этим телефоном уже есть: #{dup.id} {dup.full_name}")
    if body.contacted_on and not (today() - timedelta(days=BACKDATE_DAYS) <= body.contacted_on <= today()):
        raise bad_request(f"Дата обращения — сегодня или не раньше чем {BACKDATE_DAYS} день назад")
    lead = await create_lead(db, contacted_on=body.contacted_on, full_name=body.full_name, phone=phone, branch_id=body.branch_id, source=body.source,
                             owner_id=actor.id, assignee_id=body.assignee_id or actor.id, age=body.age,
                             parent_name=body.parent_name,
                             parent_phone=normalize_phone(body.parent_phone) if body.parent_phone else None,
                             level_id=body.level_id, notes=body.notes, next_action_at=body.next_action_at)
    await write_audit(db, actor_id=actor.id, action="lead.create", entity="lead", entity_id=lead.id, branch_id=lead.branch_id,
                      ip=actor.ip, after={"full_name": lead.full_name, "source": lead.source})
    await db.commit()
    return (await _cards(db, actor, [lead]))[0]


@router.get("/leads/{lead_id}")
async def lead_card(lead_id: int, db: DB, actor: Actor = require("crm", "view")) -> dict:
    lead = await get_lead_scoped(db, actor, lead_id)
    events = await db.scalars(select(LeadEvent).where(LeadEvent.lead_id == lead.id).order_by(LeadEvent.id.desc()).limit(200))
    attempts = await db.scalars(select(Attempt).where(Attempt.lead_id == lead.id).order_by(Attempt.id.desc()))
    events = list(events)
    names = dict((await db.execute(select(User.id, User.full_name).where(
        User.id.in_({e.actor_id for e in events if e.actor_id})))).all())
    out = []
    for e in events:
        o = EventOut.model_validate(e)
        o.actor_name = names.get(e.actor_id)
        out.append(o.model_dump())
    return {"lead": (await _card(db, actor, lead)).model_dump(),
            "events": out,
            "tests": [{"id": a.id, "score": a.score, "level_id": a.recommended_level_id, "at": a.finished_at} for a in attempts]}


@router.patch("/leads/{lead_id}", response_model=LeadCard)
async def patch_lead(lead_id: int, body: LeadPatch, db: DB, actor: Actor = require("crm", "edit")) -> LeadCard:
    lead = await get_lead_scoped(db, actor, lead_id, "edit")
    fields = list(LeadPatch.model_fields)
    before = snapshot(lead, fields)
    data = body.model_dump(exclude_unset=True)
    if branch := data.pop("branch_id", None):
        actor.ensure_branch("crm", "edit", branch)
        await set_branch(db, lead, branch, actor.id)
    if data.get("assignee_id"):
        who = await db.get(User, data["assignee_id"])
        if who is None or who.kind != UserKind.STAFF or not who.is_active or who.archived_at is not None:
            raise bad_request("Ответственным может быть только работающий сотрудник")
    for k in ("phone", "parent_phone"):
        if data.get(k):
            data[k] = normalize_phone(data[k])
    for k, v in data.items():
        setattr(lead, k, v)
    lead.last_activity_at = now()
    b, a = diff(before, snapshot(lead, fields))
    changed = [title for k, title in PATCH_TITLES.items() if k in a]
    if "assignee_id" in a:
        who = await db.get(User, lead.assignee_id) if lead.assignee_id else None
        db.add(LeadEvent(lead_id=lead.id, at=now(), kind="note", text=f"Ответственный: {who.full_name if who else 'не назначен'}",
                         actor_id=actor.id, meta={"assignee_id": lead.assignee_id}))
    if changed:
        db.add(LeadEvent(lead_id=lead.id, at=now(), kind="note", text="Изменено: " + ", ".join(changed), actor_id=actor.id, meta={}))
    await write_audit(db, actor_id=actor.id, action="lead.update", entity="lead", entity_id=lead.id, branch_id=lead.branch_id,
                      ip=actor.ip, before=b, after=a)
    await db.commit()
    return await _card(db, actor, lead)


class StageIn(In):
    stage_id: int
    lost_reason: str | None = Field(default=None, max_length=255)


@router.post("/leads/{lead_id}/stage", response_model=LeadCard)
async def change_stage(lead_id: int, body: StageIn, db: DB, actor: Actor = require("crm", "edit")) -> LeadCard:
    lead = await get_lead_scoped(db, actor, lead_id, "edit")
    st = await db.get(LeadStage, body.stage_id)
    if st is None or st.archived_at:
        raise not_found("Этап")
    if st.is_won:
        raise bad_request("«Оплатил» ставится автоматически при первой оплате")
    if st.is_lost and not body.lost_reason:
        raise bad_request("Отказ — только с причиной")
    if st.code == "trial_done":
        raise bad_request("«Пришёл на пробный» ставит учитель отметкой посещаемости")
    lead.lost_reason = body.lost_reason if st.is_lost else None
    await crm_svc.move(db, lead, st, actor.id, f"{st.name}" + (f": {body.lost_reason}" if body.lost_reason else ""))
    await write_audit(db, actor_id=actor.id, action="lead.stage", entity="lead", entity_id=lead.id, branch_id=lead.branch_id,
                      ip=actor.ip, after={"stage": st.code, "reason": body.lost_reason})
    await db.commit()
    return (await _cards(db, actor, [lead]))[0]


class EventIn(In):
    kind: str = Field(pattern="^(call|note|meeting)$")
    text: str = Field(min_length=1, max_length=4000)
    result: str | None = Field(default=None, pattern="^(booked|thinking|no_answer|refused|callback)$")
    next_action_at: datetime | None = None


@router.post("/leads/{lead_id}/events", response_model=EventOut, status_code=201)
async def add_event(lead_id: int, body: EventIn, db: DB, actor: Actor = require("crm", "edit")) -> EventOut:
    lead = await get_lead_scoped(db, actor, lead_id, "edit")
    e = LeadEvent(lead_id=lead.id, at=now(), kind=body.kind, text=body.text, actor_id=actor.id, meta={"result": body.result})
    db.add(e)
    lead.last_activity_at = now()
    if body.next_action_at:
        lead.next_action_at = body.next_action_at
    if body.kind == "call":
        contacted = await crm_svc.stage_by_code(db, "main", "contacted")
        cur = await db.get(LeadStage, lead.stage_id)
        if contacted and cur and cur.code == "new":
            await crm_svc.move(db, lead, contacted, actor.id)
    await db.commit()
    return EventOut.model_validate(e)


class TrialIn(In):
    lesson_id: int
    notify: bool = True


async def _book_trial(db: DB, actor: Actor, lead: Lead, lesson: Lesson, notify: bool) -> None:
    """Put the lead on this lesson as a trial visitor: stage, history, the WhatsApp note."""
    old_id = lead.trial_lesson_id
    lead.trial_lesson_id = lesson.id
    if old_id and old_id != lesson.id:
        # an individual trial made just for this lead and now moved: its old slot is released
        old = await db.get(Lesson, old_id)
        others = await db.scalar(select(func.count()).select_from(Lead).where(Lead.trial_lesson_id == old_id, Lead.id != lead.id))
        if (old is not None and old.is_trial and old.status == LessonStatus.PLANNED and not others):
            old.status, old.cancel_reason = LessonStatus.CANCELLED, "Пробный перенесён"
    st = await crm_svc.stage_by_code(db, "main", "trial_booked")
    loc = local(lesson.starts_at)
    if lead.stage_id == st.id:  # re-booked: the stage stays, the history still shows who moved the trial and where
        db.add(LeadEvent(lead_id=lead.id, at=now(), kind="trial", text=f"Пробный перенесён на {loc:%d.%m %H:%M}",
                         actor_id=actor.id, meta={"lesson_id": lesson.id}))
    await crm_svc.move(db, lead, st, actor.id, f"Записан на пробный {loc:%d.%m %H:%M}"
                       + (" (индивидуально)" if lesson.is_trial else ""))
    if notify and (lead.phone or lead.parent_phone):
        await send_whatsapp_text(db, lead.parent_phone or lead.phone,
                                 f"Здравствуйте! {lead.full_name} записан(а) на пробный урок {loc:%d.%m} в {loc:%H:%M}. "
                                 f"Ждём вас в One English!", template_code="trial_booked", ref=("lead", lead.id))
    await write_audit(db, actor_id=actor.id, action="lead.trial", entity="lead", entity_id=lead.id, branch_id=lead.branch_id,
                      ip=actor.ip, after={"lesson_id": lesson.id})


async def _trial_branch(db: DB, actor: Actor, lead: Lead, branch_id: int) -> None:
    if lead.branch_id is None or (branch_id != lead.branch_id and actor.scope("crm", "edit") == NETWORK):
        actor.ensure_branch("crm", "edit", branch_id)
        await set_branch(db, lead, branch_id, actor.id)  # the trial decides the branch
    elif branch_id != lead.branch_id:
        raise forbidden("Урок другого филиала")


@router.post("/leads/{lead_id}/trial", response_model=LeadCard)
async def book_trial(lead_id: int, body: TrialIn, db: DB, actor: Actor = require("crm", "edit")) -> LeadCard:
    """ТЗ 9.2: book the trial right into a group lesson (room capacity checked)."""
    lead = await get_lead_scoped(db, actor, lead_id, "edit")
    lesson = await db.get(Lesson, body.lesson_id)
    if lesson is None or lesson.status != LessonStatus.PLANNED or lesson.starts_at < now():
        raise bad_request("Выберите предстоящий урок")
    await _trial_branch(db, actor, lead, lesson.branch_id)
    room = await db.get(Room, lesson.room_id)
    members = await db.scalar(select(func.count()).select_from(GroupMember).where(
        GroupMember.group_id == lesson.group_id, GroupMember.left_on.is_(None))) if lesson.group_id else 1
    trials = await db.scalar(select(func.count()).select_from(Lead).where(Lead.trial_lesson_id == lesson.id, Lead.id != lead.id))
    if room and members + trials + 1 > room.capacity:
        raise conflict(f"В кабинете нет мест: {members + trials}/{room.capacity}")
    await _book_trial(db, actor, lead, lesson, body.notify)
    await db.commit()
    return (await _cards(db, actor, [lead]))[0]


# ---------- individual trial: the teacher's free windows ----------
SLOT_STEP = 30  # minutes between the offered start times
DAY_FROM, DAY_TO = time(8, 0), time(21, 0)  # windows are offered inside these hours


class SlotOut(BaseModel):
    starts_at: datetime
    ends_at: datetime
    room_id: int
    room_name: str


async def _free_slots(db: DB, teacher_id: int, branch_id: int, day: date, minutes: int) -> list[SlotOut]:
    """Start times on that day when the teacher has no lesson and the branch has a free room."""
    d0 = at_local(day, time(0))
    d1 = d0 + timedelta(days=1)
    rooms = list(await db.scalars(select(Room).where(Room.branch_id == branch_id, Room.archived_at.is_(None),
                                                    Room.status == "active").order_by(Room.name)))
    rooms.sort(key=lambda r: bool(r.teacher_rate))  # a room with its own teacher pay is offered last
    busy = (await db.execute(select(Lesson.starts_at, Lesson.ends_at, Lesson.room_id,
                                    func.coalesce(Lesson.actual_teacher_id, Lesson.teacher_id))
                             .where(Lesson.status != LessonStatus.CANCELLED, Lesson.starts_at < d1, Lesson.ends_at > d0))).all()
    out: list[SlotOut] = []
    s = at_local(day, DAY_FROM)
    last = at_local(day, DAY_TO)
    t = now()
    while s + timedelta(minutes=minutes) <= last:
        e = s + timedelta(minutes=minutes)
        if s > t and not any(b[3] == teacher_id and b[0] < e and b[1] > s for b in busy):
            taken = {b[2] for b in busy if b[0] < e and b[1] > s}
            room = next((r for r in rooms if r.id not in taken), None)
            if room is not None:
                out.append(SlotOut(starts_at=s, ends_at=e, room_id=room.id, room_name=room.name))
        s += timedelta(minutes=SLOT_STEP)
    return out


@router.get("/trial-slots", response_model=list[SlotOut])
async def trial_slots(teacher_id: int, branch_id: int, day: date, db: DB, minutes: int = Query(default=60, ge=30, le=120),
                      actor: Actor = require("crm", "edit")) -> list[SlotOut]:
    if day < today() or day > today() + timedelta(days=60):
        return []
    return await _free_slots(db, teacher_id, branch_id, day, minutes)


class TrialIndividualIn(In):
    teacher_id: int
    branch_id: int
    starts_at: datetime
    minutes: int = Field(default=60, ge=30, le=120)
    notify: bool = True


@router.post("/leads/{lead_id}/trial-individual", response_model=LeadCard)
async def book_individual_trial(lead_id: int, body: TrialIndividualIn, db: DB, actor: Actor = require("crm", "edit")) -> LeadCard:
    """An individual trial: a new lesson of the teacher in one of his free windows, with a free room of the branch."""
    lead = await get_lead_scoped(db, actor, lead_id, "edit")
    teacher = await db.get(User, body.teacher_id)
    if teacher is None or teacher.kind != UserKind.STAFF or not teacher.is_active or teacher.archived_at is not None:
        raise bad_request("Учитель не найден")
    if not await db.scalar(select(UserBranch.id).where(UserBranch.user_id == teacher.id, UserBranch.branch_id == body.branch_id)):
        raise bad_request("Учитель не работает в этом филиале")
    await _trial_branch(db, actor, lead, body.branch_id)
    day = local(body.starts_at).date()
    slot = next((x for x in await _free_slots(db, teacher.id, body.branch_id, day, body.minutes)
                 if x.starts_at == body.starts_at), None)
    if slot is None:
        raise conflict("Это время уже занято. Выберите другое окно")
    lesson = Lesson(branch_id=body.branch_id, teacher_id=teacher.id, room_id=slot.room_id, starts_at=slot.starts_at,
                    ends_at=slot.ends_at, topic=f"Пробный: {lead.full_name}", is_trial=True)
    db.add(lesson)
    try:
        await db.flush()
    except IntegrityError:
        raise conflict("Это время уже занято. Выберите другое окно") from None
    await _book_trial(db, actor, lead, lesson, body.notify)
    await db.commit()
    return (await _cards(db, actor, [lead]))[0]


class ConvertIn(In):
    birth_date: date | None = None
    create_account: bool = True
    guardian: GuardianIn | None = None


@router.post("/leads/{lead_id}/convert")
async def convert(lead_id: int, body: ConvertIn, db: DB, actor: Actor = require("students", "create")) -> dict:
    """Office manager turns the lead into a student card; the sale itself is the first payment."""
    lead = await get_lead_scoped(db, actor, lead_id, "view")
    if lead.student_id:
        return {"student_id": lead.student_id}
    if lead.branch_id is None:
        raise bad_request("Сначала выберите филиал лида")
    actor.ensure_branch("students", "create", lead.branch_id)
    s = Student(full_name=lead.full_name, phone=lead.phone, branch_id=lead.branch_id, level_id=lead.level_id,
                status=StudentStatus.TRIAL if lead.trial_lesson_id else StudentStatus.LEAD, source=lead.source,
                sales_user_id=lead.owner_id, lead_id=lead.id, birth_date=body.birth_date)
    db.add(s)
    await db.flush()
    if body.create_account and lead.phone and (lead.age or 18) >= 7:
        u = await upsert_portal_user(db, lead.phone, lead.full_name, "student")
        s.user_id = u.id
    guardian = body.guardian or (GuardianIn(full_name=lead.parent_name, phone=lead.parent_phone)
                                 if lead.parent_name and lead.parent_phone else None)
    if guardian:
        await add_guardian(db, s, guardian)
    lead.student_id = s.id
    db.add(LeadEvent(lead_id=lead.id, at=now(), kind="sale", text="Создана карточка ученика", actor_id=actor.id,
                     meta={"student_id": s.id}))
    await write_audit(db, actor_id=actor.id, action="lead.convert", entity="lead", entity_id=lead.id, branch_id=lead.branch_id,
                      ip=actor.ip, after={"student_id": s.id})
    await db.commit()
    return {"student_id": s.id}


class LinkStudentIn(In):
    student_id: int


@router.post("/leads/{lead_id}/link-student")
async def link_student(lead_id: int, body: LinkStudentIn, db: DB, actor: Actor = require("crm", "edit")) -> dict:
    """«Существующий ученик»: the lead is a student who wrote from Instagram/WhatsApp. No second card is made."""
    lead = await get_lead_scoped(db, actor, lead_id, "edit")
    if lead.student_id:
        raise conflict("По этому лиду уже создана карточка ученика")
    s = await get_student_scoped(db, actor, body.student_id)
    await merge_into_student(db, lead, s, actor.id)
    await write_audit(db, actor_id=actor.id, action="lead.link_student", entity="lead", entity_id=lead.id,
                      branch_id=lead.branch_id, ip=actor.ip, after={"student_id": s.id})
    await db.commit()
    return {"student_id": s.id}


@router.post("/leads/{lead_id}/archive", status_code=204)
async def archive_lead(lead_id: int, db: DB, actor: Actor = require("crm", "archive")) -> None:
    lead = await get_lead_scoped(db, actor, lead_id, "archive")
    lead.archived_at = now()
    db.add(LeadEvent(lead_id=lead.id, at=now(), kind="note", text="Лид отправлен в архив", actor_id=actor.id, meta={}))
    await write_audit(db, actor_id=actor.id, action="lead.archive", entity="lead", entity_id=lead.id, branch_id=lead.branch_id, ip=actor.ip)
    await db.commit()


class StageAccessIn(In):
    user_id: int
    stage_id: int
    level: str = Field(pattern="^(edit|own|view|none)$")


@router.get("/stage-access")
async def stage_access(db: DB, actor: Actor = require("roles", "manage")) -> dict:
    """The table «сотрудник × этап воронки». A cell narrows what the role gives: edit (as the role says), view, none."""
    stages = list(await db.scalars(select(LeadStage).join(Pipeline, Pipeline.id == LeadStage.pipeline_id)
                                   .where(LeadStage.archived_at.is_(None), Pipeline.code == "main").order_by(LeadStage.order)))
    rows = (await db.execute(
        select(User.id, User.full_name, Role.name, RolePermission.module, RolePermission.action)
        .join(UserRole, UserRole.user_id == User.id).join(Role, Role.id == UserRole.role_id)
        .join(RolePermission, RolePermission.role_id == Role.id)
        .where(User.kind == UserKind.STAFF, User.is_active.is_(True), User.archived_at.is_(None), Role.archived_at.is_(None),
               ((RolePermission.module == "crm") & RolePermission.action.in_(("view", "edit")))
               | ((RolePermission.module == "roles") & (RolePermission.action == "manage")))
        .order_by(User.full_name))).all()
    users: dict[int, dict] = {}
    for uid, name, role, module, action in rows:
        u = users.setdefault(uid, {"id": uid, "full_name": name, "roles": [], "view": False, "edit": False, "admin": False})
        if role not in u["roles"]:
            u["roles"].append(role)
        u["admin" if module == "roles" else action] = True
    cells = {f"{uid}:{sid}": level for uid, sid, level in await db.execute(
        select(LeadStageAccess.user_id, LeadStageAccess.stage_id, LeadStageAccess.level))}
    return {"stages": [{"id": s.id, "name": s.name, "code": s.code} for s in stages],
            "users": [{"id": u["id"], "full_name": u["full_name"], "roles": u["roles"], "can_edit": u["edit"], "locked": u["admin"]}
                      for u in users.values() if u["view"]],
            "cells": cells}


@router.put("/stage-access", status_code=204)
async def set_stage_access(body: StageAccessIn, db: DB, actor: Actor = require("roles", "manage")) -> None:
    user, stage = await db.get(User, body.user_id), await db.get(LeadStage, body.stage_id)
    if user is None or user.kind != UserKind.STAFF or stage is None:
        raise not_found("Сотрудник или этап")
    row = await db.scalar(select(LeadStageAccess).where(LeadStageAccess.user_id == user.id, LeadStageAccess.stage_id == stage.id))
    before = row.level if row else "edit"
    if body.level == "edit":
        if row:
            await db.delete(row)
    elif row:
        row.level = body.level
    else:
        db.add(LeadStageAccess(user_id=user.id, stage_id=stage.id, level=body.level))
    await write_audit(db, actor_id=actor.id, action="crm.stage_access", entity="user", entity_id=user.id, ip=actor.ip,
                      before={"stage": stage.name, "level": before}, after={"stage": stage.name, "level": body.level})
    await db.commit()


@router.get("/analytics")
async def analytics(db: DB, actor: Actor = require("crm", "view"), date_from: date | None = None, date_to: date | None = None,
                    branch_id: int | None = None) -> dict:
    """ТЗ 9.4: conversion by stage, source, owner and branch; loss reasons."""
    d1 = date_from or (today() - timedelta(days=30))
    d2 = date_to or today()
    start, end = local_range(d1, d2)
    q = select(Lead).where(lead_filter(actor), Lead.created_at >= start, Lead.created_at < end)
    if branch_id:
        q = q.where(Lead.branch_id == branch_id)
    leads = list(await db.scalars(q))
    stages = {s.id: s for s in await db.scalars(select(LeadStage))}
    events = list(await db.scalars(select(LeadEvent).where(LeadEvent.lead_id.in_([x.id for x in leads]), LeadEvent.kind == "stage")))
    reached: dict[int, set[str]] = {}
    for e in events:
        st = stages.get((e.meta or {}).get("to"))
        if st:
            reached.setdefault(e.lead_id, set()).add(st.code)
    order = ["new", "contacted", "trial_booked", "trial_done", "paid"]

    def funnel(subset: list[Lead]) -> dict:
        res = {}
        for i, code in enumerate(order):
            res[code] = sum(1 for x in subset if i == 0 or code in reached.get(x.id, set())
                            or any(c in reached.get(x.id, set()) for c in order[i + 1:]))
        res["lost"] = sum(1 for x in subset if stages.get(x.stage_id) and stages[x.stage_id].is_lost)
        res["conversion"] = round(100 * res["paid"] / len(subset), 1) if subset else 0.0
        return res

    def group_by(key) -> dict:
        g: dict = {}
        for x in leads:
            g.setdefault(key(x), []).append(x)
        return {str(k): funnel(v) for k, v in g.items()}

    reasons: dict[str, int] = {}
    for x in leads:
        if x.lost_reason:
            reasons[x.lost_reason] = reasons.get(x.lost_reason, 0) + 1
    names = dict((await db.execute(select(User.id, User.full_name).where(User.id.in_({x.owner_id for x in leads if x.owner_id})))).all())
    return {"period": [d1, d2], "total": funnel(leads), "by_source": group_by(lambda x: x.source),
            "by_owner": [{"user_id": int(k) if k != "None" else None, "name": names.get(int(k)) if k != "None" else None, **v}
                         for k, v in group_by(lambda x: x.owner_id).items()],
            "by_branch": group_by(lambda x: x.branch_id), "lost_reasons": dict(sorted(reasons.items(), key=lambda kv: -kv[1]))}


# ---- «Откуда узнал»: lead sources, edited on the Справочники page ----
# Built-in codes stay valid forever (the inbox, QR test, import and the «Возврат» funnel set them);
# they can be renamed or hidden from pickers. Own sources get codes s1, s2… Stored in settings["lead_sources"].
BUILTIN_SOURCES = {
    LeadSource.INSTAGRAM: "Instagram", LeadSource.WHATSAPP: "WhatsApp", LeadSource.QR: "QR-тест", LeadSource.SITE: "Сайт",
    LeadSource.REFERRAL: "Рекомендация", LeadSource.WALK_IN: "Пришёл сам", LeadSource.SALES: "Звонок / офис",
    LeadSource.RETURN: "Возврат", LeadSource.IMPORT: "Импорт из таблицы",
}
# Set by the system itself: renamable, never hidden from lists.
SYSTEM_SOURCES = {LeadSource.INSTAGRAM, LeadSource.WHATSAPP, LeadSource.QR, LeadSource.RETURN, LeadSource.IMPORT}
SOURCES_KEY = "lead_sources"


class SourceOut(BaseModel):
    code: str
    name: str
    system: bool = False
    builtin: bool = False
    hidden: bool = False


class SourceIn(In):
    name: str = Field(min_length=2, max_length=60)


async def _source_rows(db) -> tuple[list[dict], "Setting | None"]:
    from app.models import Setting

    row = await db.scalar(select(Setting).where(Setting.key == SOURCES_KEY))
    import copy

    # A deep copy: editing in place would make the JSON column look unchanged and nothing would be saved.
    return (copy.deepcopy(list((row.value or {}).get("v") or [])) if row else []), row


async def list_sources(db) -> list[SourceOut]:
    stored, _ = await _source_rows(db)
    by = {x["code"]: x for x in stored if isinstance(x, dict) and x.get("code")}
    out = [SourceOut(code=c, name=by.get(c, {}).get("name") or n, system=c in SYSTEM_SOURCES, builtin=True,
                     hidden=bool(by.get(c, {}).get("hidden")) and c not in SYSTEM_SOURCES)
           for c, n in BUILTIN_SOURCES.items()]
    out += [SourceOut(code=c, name=x.get("name") or c, hidden=bool(x.get("hidden"))) for c, x in by.items() if c not in BUILTIN_SOURCES]
    return out


async def valid_source(db, code: str) -> bool:
    return code in LeadSource.ALL or any(s.code == code for s in await list_sources(db))


async def _save_sources(db, actor: Actor, rows: list[dict], note: str) -> None:
    from app.models import Setting

    _, row = await _source_rows(db)
    if row is None:
        row = Setting(key=SOURCES_KEY, value={"v": rows}, updated_by=actor.id)
        db.add(row)
    else:
        row.value, row.updated_by = {"v": rows}, actor.id
    await db.flush()
    await write_audit(db, actor_id=actor.id, action="lead_source." + note, entity="setting", entity_id=row.id, ip=actor.ip,
                      after={"v": rows})
    await db.commit()


@router.get("/sources", response_model=list[SourceOut])
async def get_sources(db: DB, actor: Actor = require_staff()) -> list[SourceOut]:
    return await list_sources(db)


@router.post("/sources", response_model=SourceOut, status_code=201)
async def add_source(body: SourceIn, db: DB, actor: Actor = require("settings", "edit")) -> SourceOut:
    name = body.name.strip()
    if any(s.name.lower() == name.lower() and not s.hidden for s in await list_sources(db)):
        raise bad_request("Такой источник уже есть")
    stored, _ = await _source_rows(db)
    n = 1 + max([int(x["code"][1:]) for x in stored if str(x.get("code", "")).startswith("s") and x["code"][1:].isdigit()] or [0])
    stored.append({"code": f"s{n}", "name": name})
    await _save_sources(db, actor, stored, "create")
    return SourceOut(code=f"s{n}", name=name)


async def _update_source(db, actor: Actor, code: str, **changes) -> None:
    if not any(s.code == code for s in await list_sources(db)):
        raise not_found("Источник")
    stored, _ = await _source_rows(db)
    for x in stored:
        if x.get("code") == code:
            x.update(changes)
            break
    else:
        stored.append({"code": code, **changes})
    await _save_sources(db, actor, stored, "update")


@router.patch("/sources/{code}", response_model=SourceOut)
async def rename_source(code: str, body: SourceIn, db: DB, actor: Actor = require("settings", "edit")) -> SourceOut:
    await _update_source(db, actor, code, name=body.name.strip())
    return next(s for s in await list_sources(db) if s.code == code)


@router.post("/sources/{code}/archive", status_code=204)
async def archive_source(code: str, db: DB, actor: Actor = require("settings", "edit")) -> None:
    """Hidden from pickers; leads that already have it keep it and still show its name."""
    if code in SYSTEM_SOURCES:
        raise bad_request("Этот источник система ставит сама, его можно только переименовать")
    await _update_source(db, actor, code, hidden=True)
