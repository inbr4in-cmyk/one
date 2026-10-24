"""Background jobs. Run `python -m app.jobs loop` as a separate process next to the API.

`minutely` — attendance reminders, stale-lead alerts, WhatsApp retries.
`nightly`  — lesson generation horizon, «Ушёл» after N days → return funnel, non-payment access block.
Every job is idempotent: running it twice sends nothing twice.
"""

import asyncio
import logging
import sys
from datetime import datetime, timedelta

from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit
from app.core.db import SessionLocal
from app.core.kv import get_kv
from app.models import BalanceEntry, GroupMember, Lead, LeadStage, Lesson, Student, Task, TaskAssignee
from app.models.work import TaskStatus
from app.models.learning import LessonStatus, StudentStatus
from app.modules.academics.schedule import extend_all
from app.modules.crm.service import create_lead, crm_people
from app.services.clock import at_local, end_of_local_day, local, now, today
from app.services.messaging import notify_user, retry_failed
from app.services.values import setting

log = logging.getLogger("jobs")
DAY = 86400


async def once(key: str, ttl: int = 7 * DAY) -> bool:
    """True the first time a key is seen within ttl."""
    kv = get_kv()
    if await kv.get(f"once:{key}"):
        return False
    await kv.set(f"once:{key}", "1", ttl)
    return True


# ---------- minutely ----------
async def attendance_reminders(db: AsyncSession) -> int:
    """ТЗ 6: teacher is reminded N min after the lesson; admins are alerted if it's still unmarked later."""
    remind = int(await setting(db, "attendance_reminder_min"))
    alert = int(await setting(db, "attendance_admin_alert_min"))
    t = now()
    rows = await db.scalars(select(Lesson).where(
        Lesson.status == LessonStatus.PLANNED, Lesson.attendance_marked_at.is_(None),
        Lesson.ends_at <= t - timedelta(minutes=remind), Lesson.ends_at > t - timedelta(days=1)))
    sent = 0
    for lesson in rows:
        teacher = lesson.actual_teacher_id or lesson.teacher_id
        when = local(lesson.starts_at).strftime("%d.%m %H:%M")
        if await once(f"att-remind:{lesson.id}"):
            await notify_user(db, teacher, "attendance", "Отметьте посещаемость", body=f"Урок {when} ещё не отмечен",
                              link=f"/lessons/{lesson.id}")
            sent += 1
        if lesson.ends_at <= t - timedelta(minutes=alert) and await once(f"att-alert:{lesson.id}"):
            for uid in await crm_people(db, lesson.branch_id, "attendance", "edit_past"):
                if uid != teacher:
                    await notify_user(db, uid, "attendance", "Посещаемость не отмечена",
                                      body=f"Урок {when}: учитель не отметил посещаемость", link=f"/lessons/{lesson.id}")
                    sent += 1
    return sent


async def stale_leads(db: AsyncSession) -> int:
    """A lead sitting in a stage longer than the stage allows (ТЗ 9: new lead → 1 h) pings its manager once per stage."""
    t = now()
    rows = (await db.execute(
        select(Lead, LeadStage).join(LeadStage, LeadStage.id == Lead.stage_id).where(
            Lead.archived_at.is_(None), LeadStage.is_won.is_(False), LeadStage.is_lost.is_(False),
            LeadStage.stale_after_hours.is_not(None),
            Lead.stage_changed_at < t - func.make_interval(0, 0, 0, 0, LeadStage.stale_after_hours),
            or_(Lead.last_activity_at.is_(None),
                Lead.last_activity_at < t - func.make_interval(0, 0, 0, 0, LeadStage.stale_after_hours)))
        .limit(500)
    )).all()
    sent = 0
    for lead, stage in rows:
        if not await once(f"stale:{lead.id}:{stage.id}:{int(lead.stage_changed_at.timestamp())}"):
            continue
        targets = [lead.assignee_id] if lead.assignee_id else await crm_people(db, lead.branch_id, "crm")
        for uid in targets:
            await notify_user(db, uid, "lead_stale", f"Лид ждёт: {lead.full_name}",
                              body=f"«{stage.name}» дольше {stage.stale_after_hours} ч", link=f"/crm/leads/{lead.id}")
            sent += 1
    return sent


async def overdue_tasks(db: AsyncSession) -> int:
    rows = await db.scalars(select(Task).where(
        Task.archived_at.is_(None), Task.due_at < now(), Task.due_at > now() - timedelta(days=7),
        Task.status.not_in((TaskStatus.DONE, TaskStatus.CANCELLED, TaskStatus.REVIEW))))
    sent = 0
    for t in rows:
        if not await once(f"task-overdue:{t.id}:{int(t.due_at.timestamp())}"):
            continue
        for uid in set(await db.scalars(select(TaskAssignee.user_id).where(TaskAssignee.task_id == t.id))) | {t.creator_id}:
            await notify_user(db, uid, "task", f"Просрочена задача: {t.title}", link=f"/tasks/{t.id}")
            sent += 1
    return sent


async def minutely(db: AsyncSession) -> dict:
    out = {"attendance": await attendance_reminders(db), "stale_leads": await stale_leads(db),
           "overdue_tasks": await overdue_tasks(db)}
    await db.commit()
    out["wa_retried"] = await retry_failed(db)
    await db.commit()
    return out


# ---------- nightly ----------
async def mark_left(db: AsyncSession) -> int:
    """No group and no visit for N days → «Ушёл», and a card in the return funnel."""
    days = int(await setting(db, "left_after_days"))
    cutoff = now() - timedelta(days=days)
    in_group = exists().where(GroupMember.student_id == Student.id, GroupMember.left_on.is_(None))
    rows = await db.scalars(select(Student).where(
        Student.archived_at.is_(None), Student.status.in_((StudentStatus.ACTIVE, StudentStatus.FINISHED)), ~in_group,
        func.coalesce(Student.last_visit_at, Student.created_at) < cutoff).limit(500))
    n = 0
    for s in rows:
        s.status, s.left_at = StudentStatus.LEFT, now()
        lead = await create_lead(db, full_name=s.full_name, phone=s.phone, branch_id=s.branch_id, source="return",
                                 owner_id=None, assignee_id=s.sales_user_id, pipeline="return", stage="left",
                                 student_id=s.id, level_id=s.level_id)
        await write_audit(db, actor_id=None, action="student.left", entity="student", entity_id=s.id,
                          branch_id=s.branch_id, after={"return_lead_id": lead.id}, note=f"Нет занятий {days} дней")
        n += 1
    return n


async def block_nonpayers(db: AsyncSession) -> int:
    """Rules: no payment within N days after lessons ran out → portal access is blocked until payment."""
    days = int(await setting(db, "nonpayment_block_days"))
    cutoff = now() - timedelta(days=days)
    rows = await db.scalars(select(Student).where(
        Student.archived_at.is_(None), Student.access_blocked_at.is_(None), Student.lessons_left <= 0,
        Student.status == StudentStatus.ACTIVE))
    n = 0
    for s in rows:
        last_positive = await db.scalar(select(func.max(BalanceEntry.id)).where(
            BalanceEntry.student_id == s.id, BalanceEntry.lessons_after > 0))
        ran_out = await db.scalar(select(func.min(BalanceEntry.at)).where(
            BalanceEntry.student_id == s.id, BalanceEntry.id > (last_positive or 0)))
        if ran_out is None or ran_out > cutoff or (s.last_payment_at and s.last_payment_at > ran_out):
            continue
        s.access_blocked_at = now()
        await write_audit(db, actor_id=None, action="student.blocked", entity="student", entity_id=s.id,
                          branch_id=s.branch_id, note=f"Нет оплаты {days} дней после окончания уроков")
        n += 1
    return n


async def spawn_recurring_tasks(db: AsyncSession) -> int:
    """A recurring task is a template: each day (or its weekday) a fresh copy goes to the same people."""
    d = today()
    start = at_local(d, datetime.min.time())
    n = 0
    for tpl in await db.scalars(select(Task).where(Task.archived_at.is_(None), Task.recurrence.is_not(None),
                                                   Task.parent_task_id.is_(None))):
        if tpl.recurrence == "weekly" and local(tpl.created_at).weekday() != d.weekday():
            continue
        if await db.scalar(select(Task.id).where(Task.parent_task_id == tpl.id, Task.created_at >= start)):
            continue
        due = (at_local(d, local(tpl.due_at).time()) if tpl.due_at else end_of_local_day(now()))
        copy = Task(title=tpl.title, description=tpl.description, creator_id=tpl.creator_id, branch_id=tpl.branch_id,
                    priority=tpl.priority, due_at=due, status=TaskStatus.NEW, link_type=tpl.link_type, link_id=tpl.link_id,
                    parent_task_id=tpl.id)
        db.add(copy)
        await db.flush()
        for uid in await db.scalars(select(TaskAssignee.user_id).where(TaskAssignee.task_id == tpl.id)):
            db.add(TaskAssignee(task_id=copy.id, user_id=uid))
            await notify_user(db, uid, "task", f"Задача на сегодня: {copy.title}", link=f"/tasks/{copy.id}")
        n += 1
    return n


async def nightly(db: AsyncSession) -> dict:
    out = {"lessons": await extend_all(db), "tasks": await spawn_recurring_tasks(db)}
    await db.commit()
    out["left"] = await mark_left(db)
    out["blocked"] = await block_nonpayers(db)
    await db.commit()
    return out


async def _run(job) -> dict:
    async with SessionLocal() as db:
        return await job(db)


async def loop() -> None:
    last_night = None
    while True:
        try:
            log.info("minutely %s", await _run(minutely))
            t = local(now())
            if t.hour == 3 and last_night != t.date():
                log.info("nightly %s", await _run(nightly))
                last_night = t.date()
        except Exception:
            log.exception("job failed")
        await asyncio.sleep(60)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    cmd = sys.argv[1] if len(sys.argv) > 1 else "loop"
    if cmd == "loop":
        asyncio.run(loop())
    else:
        print(asyncio.run(_run({"minutely": minutely, "nightly": nightly}[cmd])))
