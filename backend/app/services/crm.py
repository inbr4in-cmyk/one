from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Lead, LeadEvent, LeadStage, Lesson, Pipeline
from app.services.clock import local, now
from app.services.messaging import notify_user
from app.services.payroll import accrue_once
from app.services.values import rate


async def stage_by_code(db: AsyncSession, pipeline_code: str, stage_code: str) -> LeadStage | None:
    return await db.scalar(
        select(LeadStage).join(Pipeline, Pipeline.id == LeadStage.pipeline_id)
        .where(Pipeline.code == pipeline_code, LeadStage.code == stage_code, LeadStage.archived_at.is_(None))
    )


async def move(db: AsyncSession, lead: Lead, stage: LeadStage, actor_id: int | None, text: str | None = None) -> None:
    if lead.stage_id == stage.id:
        return
    old = lead.stage_id
    lead.stage_id = stage.id
    lead.pipeline_id = stage.pipeline_id
    lead.stage_changed_at = now()
    lead.last_activity_at = now()
    db.add(LeadEvent(lead_id=lead.id, at=now(), kind="stage", text=text or stage.name, actor_id=actor_id,
                     meta={"from": old, "to": stage.id}))


async def on_trial_attended(db: AsyncSession, lead: Lead, lesson: Lesson, actor_id: int) -> None:
    """ТЗ 9.2: the teacher marks the trial visit → lead moves to «Пришёл на пробный» and the sales person who
    brought the lead gets the trial bonus — once per lead, however many times attendance is re-marked."""
    stage = await stage_by_code(db, "main", "trial_done")
    if stage:
        await move(db, lead, stage, actor_id, "Пришёл на пробный урок")
    lead.trial_lesson_id = lesson.id
    if lead.owner_id:
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
