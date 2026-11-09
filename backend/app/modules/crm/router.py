from datetime import date, datetime, timedelta

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.core.query import icontains
from app.core.audit import diff, snapshot, write_audit
from app.core.deps import DB, Actor, require
from app.core.errors import bad_request, conflict, forbidden, not_found
from app.core.permissions import NETWORK
from app.core.schemas import In, ORM
from app.core.security import mask_phone, normalize_phone
from app.models import Attempt, Conversation, ExternalContact, GroupMember, Lead, LeadEvent, LeadStage, Lesson, Pipeline, Room, Student, User
from app.models.crm import LeadSource
from app.models.learning import LessonStatus, StudentStatus
from app.modules.crm.service import create_lead, find_by_phone, get_lead_scoped, lead_filter
from app.modules.students.router import add_guardian, upsert_portal_user
from app.modules.students.schemas import GuardianIn
from app.services import crm as crm_svc
from app.services.clock import local, local_range, now, today
from app.services.messaging import send_whatsapp_text
from app.services.values import setting

router = APIRouter(prefix="/crm", tags=["crm"])


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


class LeadCard(BaseModel):
    id: int
    full_name: str
    phone: str | None
    age: int | None
    parent_name: str | None
    parent_phone: str | None
    branch_id: int
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


class EventOut(ORM):
    id: int
    at: datetime
    kind: str
    text: str | None
    actor_id: int | None
    meta: dict


def _phone(actor: Actor, phone: str | None) -> str | None:
    return phone if actor.can("students", "view_contacts") or actor.can("crm", "edit") else mask_phone(phone)


async def _cards(db: DB, actor: Actor, leads: list[Lead]) -> list[LeadCard]:
    if not leads:
        return []
    stages = {s.id: s for s in await db.scalars(select(LeadStage))}
    owners = dict((await db.execute(select(User.id, User.full_name).where(User.id.in_({x.owner_id for x in leads if x.owner_id})))).all())
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
        stmt = stmt.where(Lead.branch_id == branch_id)
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
    if body.source not in LeadSource.ALL:
        raise bad_request("Неизвестный источник")
    phone = normalize_phone(body.phone) if body.phone else None
    if dup := await find_by_phone(db, phone):
        raise conflict(f"Лид с этим телефоном уже есть: #{dup.id} {dup.full_name}")
    lead = await create_lead(db, full_name=body.full_name, phone=phone, branch_id=body.branch_id, source=body.source,
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
    return {"lead": (await _cards(db, actor, [lead]))[0].model_dump(),
            "events": [EventOut.model_validate(e).model_dump() for e in events],
            "tests": [{"id": a.id, "score": a.score, "level_id": a.recommended_level_id, "at": a.finished_at} for a in attempts]}


@router.patch("/leads/{lead_id}", response_model=LeadCard)
async def patch_lead(lead_id: int, body: LeadPatch, db: DB, actor: Actor = require("crm", "edit")) -> LeadCard:
    lead = await get_lead_scoped(db, actor, lead_id, "edit")
    fields = list(LeadPatch.model_fields)
    before = snapshot(lead, fields)
    data = body.model_dump(exclude_unset=True)
    for k in ("phone", "parent_phone"):
        if data.get(k):
            data[k] = normalize_phone(data[k])
    for k, v in data.items():
        setattr(lead, k, v)
    lead.last_activity_at = now()
    b, a = diff(before, snapshot(lead, fields))
    await write_audit(db, actor_id=actor.id, action="lead.update", entity="lead", entity_id=lead.id, branch_id=lead.branch_id,
                      ip=actor.ip, before=b, after=a)
    await db.commit()
    return (await _cards(db, actor, [lead]))[0]


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


@router.post("/leads/{lead_id}/trial", response_model=LeadCard)
async def book_trial(lead_id: int, body: TrialIn, db: DB, actor: Actor = require("crm", "edit")) -> LeadCard:
    """ТЗ 9.2: book the trial right into a group lesson (room capacity checked)."""
    lead = await get_lead_scoped(db, actor, lead_id, "edit")
    lesson = await db.get(Lesson, body.lesson_id)
    if lesson is None or lesson.status != LessonStatus.PLANNED or lesson.starts_at < now():
        raise bad_request("Выберите предстоящий урок")
    if lesson.branch_id != lead.branch_id and actor.scope("crm", "edit") != NETWORK:
        raise forbidden("Урок другого филиала")
    room = await db.get(Room, lesson.room_id)
    members = await db.scalar(select(func.count()).select_from(GroupMember).where(
        GroupMember.group_id == lesson.group_id, GroupMember.left_on.is_(None))) if lesson.group_id else 1
    trials = await db.scalar(select(func.count()).select_from(Lead).where(Lead.trial_lesson_id == lesson.id, Lead.id != lead.id))
    if room and members + trials + 1 > room.capacity:
        raise conflict(f"В кабинете нет мест: {members + trials}/{room.capacity}")
    lead.trial_lesson_id = lesson.id
    st = await crm_svc.stage_by_code(db, "main", "trial_booked")
    loc = local(lesson.starts_at)
    await crm_svc.move(db, lead, st, actor.id, f"Пробный {loc:%d.%m %H:%M}")
    if body.notify and (lead.phone or lead.parent_phone):
        await send_whatsapp_text(db, lead.parent_phone or lead.phone,
                                 f"Здравствуйте! {lead.full_name} записан(а) на пробный урок {loc:%d.%m} в {loc:%H:%M}. "
                                 f"Ждём вас в One English!", template_code="trial_booked", ref=("lead", lead.id))
    await write_audit(db, actor_id=actor.id, action="lead.trial", entity="lead", entity_id=lead.id, branch_id=lead.branch_id,
                      ip=actor.ip, after={"lesson_id": lesson.id})
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


@router.post("/leads/{lead_id}/archive", status_code=204)
async def archive_lead(lead_id: int, db: DB, actor: Actor = require("crm", "archive")) -> None:
    lead = await get_lead_scoped(db, actor, lead_id, "archive")
    lead.archived_at = now()
    await write_audit(db, actor_id=actor.id, action="lead.archive", entity="lead", entity_id=lead.id, branch_id=lead.branch_id, ip=actor.ip)
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
