from datetime import timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Conversation, ExternalContact, Lead, LeadEvent, LeadStage, Lesson, Pipeline, User
from app.services.clock import local, now
from app.services.messaging import notify_user
from app.services.payroll import accrue_once
from app.services.values import rate


async def stage_by_code(db: AsyncSession, pipeline_code: str, stage_code: str) -> LeadStage | None:
    return await db.scalar(
        select(LeadStage).join(Pipeline, Pipeline.id == LeadStage.pipeline_id)
        .where(Pipeline.code == pipeline_code, LeadStage.code == stage_code, LeadStage.archived_at.is_(None))
    )


async def no_answer_stage(db: AsyncSession, pipeline: str = "main") -> LeadStage | None:
    """«Недозвон»: the school adds it in Справочники, so it is found by its name (or the code on a new install)."""
    return await db.scalar(
        select(LeadStage).join(Pipeline, Pipeline.id == LeadStage.pipeline_id)
        .where(Pipeline.code == pipeline, LeadStage.archived_at.is_(None),
               or_(LeadStage.code == "no_answer", func.lower(LeadStage.name) == "недозвон")).order_by(LeadStage.id).limit(1))


async def got_in_touch(db: AsyncSession, lead: Lead, actor_id: int | None, text: str | None = None, answered: bool = True) -> None:
    """A call or a reply: «Новая заявка» → «Недозвон» when nobody answered, «Новая заявка»/«Недозвон» → contacted otherwise.
    The same in «Возврат» (owner, 27.11.2026): «Ушёл» → «Недозвон» → «Связались»."""
    cur = await db.get(LeadStage, lead.stage_id)
    if cur is None:
        return
    pipe = await db.scalar(select(Pipeline.code).where(Pipeline.id == cur.pipeline_id))
    if pipe not in ("main", "return"):
        return
    first = "new" if pipe == "main" else "left"
    na = await no_answer_stage(db, pipe)
    if not answered and na is not None:
        if cur.code == first:
            await move(db, lead, na, actor_id, text)
        return
    if cur.code == first or (na is not None and cur.id == na.id):
        contacted = await stage_by_code(db, pipe, "contacted")
        if contacted:
            await move(db, lead, contacted, actor_id, text)


async def move(db: AsyncSession, lead: Lead, stage: LeadStage, actor_id: int | None, text: str | None = None) -> None:
    if lead.stage_id == stage.id:
        return
    old = lead.stage_id
    lead.stage_id = stage.id
    lead.pipeline_id = stage.pipeline_id
    lead.stage_changed_at = now()
    lead.last_activity_at = now()
    # The new stage's clock: the manager has work_hours to leave a note / call / book. On «Записан на пробный»
    # it starts later, when the client did not come (jobs.lead_control).
    timed = stage.work_hours and stage.code != "trial_booked" and not (stage.is_won or stage.is_lost)
    lead.work_due_at = now() + timedelta(hours=stage.work_hours) if timed else None
    if stage.is_won or stage.is_lost:
        lead.free_since = None
        # a closed lead needs no next step: its open tasks are closed with it
        from app.models import Task
        from app.models.work import TaskStatus

        for t in await db.scalars(select(Task).where(Task.link_type == "lead", Task.link_id == lead.id, Task.archived_at.is_(None),
                                                     Task.status.not_in((TaskStatus.DONE, TaskStatus.CANCELLED)))):
            t.status = TaskStatus.CANCELLED
        lead.next_action_at = None
    db.add(LeadEvent(lead_id=lead.id, at=now(), kind="stage", text=text or stage.name, actor_id=actor_id,
                     meta={"from": old, "to": stage.id}))


MANUAL = ("note", "call", "meeting")  # what a manager writes himself; such events carry meta["result"]


def manual_event():
    return LeadEvent.kind.in_(MANUAL) & LeadEvent.meta.has_key("result")


async def alert(db: AsyncSession, user_id: int, kind: str, title: str, body: str | None = None, link: str | None = None) -> None:
    """A notification that also pops up on the person's screen right away."""
    from app.services.realtime import publish

    await notify_user(db, user_id, kind, title, body=body, link=link)
    await publish(f"user:{user_id}", {"type": "alert", "kind": kind, "title": title, "body": body, "link": link})


async def worked(db: AsyncSession, lead: Lead, actor_id: int | None) -> None:
    """A manager worked the lead (note, call, trial booking, reply to the client): the deadline is met. If the lead
    was free, the one who worked it becomes responsible — for the lead and for its Instagram/WhatsApp chat."""
    lead.work_due_at = None
    if lead.free_since is None or actor_id is None:
        return
    lead.free_since = None
    if lead.assignee_id == actor_id:
        return
    lead.assignee_id = actor_id
    who = await db.get(User, actor_id)
    for conv in await db.scalars(select(Conversation).join(ExternalContact, ExternalContact.id == Conversation.contact_id)
                                 .where(ExternalContact.lead_id == lead.id)):
        conv.assignee_id = actor_id
    db.add(LeadEvent(lead_id=lead.id, at=now(), kind="note", actor_id=actor_id, meta={"assignee_id": actor_id, "took_free": True},
                     text=f"Ответственный: {who.full_name if who else ''} (взял свободный лид)"))


async def on_trial_attended(db: AsyncSession, lead: Lead, lesson: Lesson, actor_id: int) -> None:
    """ТЗ 9.2: the teacher marks the trial visit → lead moves to «Пришёл на пробный» and the sales person who
    brought the lead gets the trial bonus — once per lead, however many times attendance is re-marked."""
    stage = await stage_by_code(db, "main", "trial_done")
    if stage:
        await move(db, lead, stage, actor_id, "Пришёл на пробный урок")
    lead.trial_lesson_id = lesson.id
    from app.services import retention

    if lead.owner_id and not await retention.no_trial_bonus(db, lead.owner_id):
        d = local(lesson.starts_at).date()
        created = await accrue_once(db, user_id=lead.owner_id, kind="trial_visit", amount=await rate(db, "sales_trial_visit", d),
                                    ref=("lead", lead.id), on=d, branch_id=lead.branch_id,
                                    description=f"Пробный урок: {lead.full_name}", created_by=actor_id)
        if created:
            await notify_user(db, lead.owner_id, "kpi", f"{lead.full_name} пришёл на пробный — бонус начислен",
                              link=f"/crm/leads/{lead.id}")
    if lead.assignee_id:
        await notify_user(db, lead.assignee_id, "lead", f"{lead.full_name} был на пробном. Свяжитесь сегодня",
                          link=f"/crm/leads/{lead.id}")
