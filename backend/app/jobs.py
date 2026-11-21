"""Background jobs. Run `python -m app.jobs loop` as a separate process next to the API.

`minutely` — attendance reminders, stale-lead alerts, WhatsApp retries.
`nightly`  — lesson generation horizon, «Ушёл» after N days → return funnel, non-payment access block.
Every job is idempotent: running it twice sends nothing twice.
"""

import asyncio
import logging
import sys
import time
from datetime import datetime, timedelta

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit
from app.core.db import SessionLocal
from app.core.kv import get_kv
from app.models import (
    Attendance, BalanceEntry, Complaint, Expense, Freeze, GroupMember, Lead, LeadEvent, LeadStage, Lesson, Student, Task,
    TaskAssignee,
)
from app.models.learning import AttendanceStatus
from app.models.work import TaskStatus
from app.models.learning import LessonStatus, StudentStatus
from app.modules.academics.schedule import extend_all
from app.modules.crm.service import create_lead, crm_people
from app.services.clock import at_local, end_of_local_day, local, now, period_of, today
from app.services import bookpay
from app.services.coins import award_auto
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


def _day_time(t: datetime) -> bool:
    return 9 <= local(t).hour < 21  # nobody is pinged about idle leads at night


async def lead_control(db: AsyncSession) -> dict:
    """Owner's rules 21.11.2026. (1) The client did not come to the trial: the responsible manager is told at once and
    has the stage's hours to get in touch. (2) A deadline missed on any timed stage: the lead becomes free, every
    manager of the branch sees it and is told; who works it first becomes responsible. (3) A lead with no note and no
    task for N hours: its manager is told to work it."""
    from app.models import Attendance
    from app.models.learning import AttendanceStatus
    from app.services import crm

    t = now()
    out = {"noshow": 0, "freed": 0, "idle": 0}
    booked = await crm.stage_by_code(db, "main", "trial_booked")
    if booked and booked.work_hours:
        rows = (await db.execute(select(Lead, Lesson).join(Lesson, Lesson.id == Lead.trial_lesson_id).where(
            Lead.stage_id == booked.id, Lead.archived_at.is_(None), Lead.work_due_at.is_(None), Lead.free_since.is_(None),
            Lesson.ends_at <= t, Lesson.ends_at > t - timedelta(days=2), Lesson.status != LessonStatus.CANCELLED))).all()
        for lead, lesson in rows:
            att = await db.scalar(select(Attendance.status).where(Attendance.lesson_id == lesson.id, Attendance.lead_id == lead.id))
            if att in (AttendanceStatus.PRESENT, AttendanceStatus.LATE):
                continue
            if att is None and lesson.attendance_marked_at is None and lesson.ends_at > t - timedelta(hours=1):
                continue  # the teacher has an hour to mark who came
            if not await once(f"noshow:{lead.id}:{lesson.id}"):
                continue
            when = local(lesson.starts_at).strftime("%d.%m %H:%M")
            lead.work_due_at = t + timedelta(hours=booked.work_hours)
            db.add(LeadEvent(lead_id=lead.id, at=t, kind="trial", text=f"Не пришёл на пробный {when}", actor_id=None,
                             meta={"lesson_id": lesson.id, "noshow": True}))
            for uid in [lead.assignee_id] if lead.assignee_id else await crm_people(db, lead.branch_id, "crm"):
                await crm.alert(db, uid, "lead", f"{lead.full_name} не пришёл на пробный",
                                body="Свяжитесь с клиентом: узнайте причину, запишите на другой день и оставьте заметку",
                                link=f"/crm/leads/{lead.id}")
            out["noshow"] += 1
    rows = (await db.execute(select(Lead, LeadStage).join(LeadStage, LeadStage.id == Lead.stage_id).where(
        Lead.archived_at.is_(None), Lead.free_since.is_(None), Lead.work_due_at <= t,
        LeadStage.is_won.is_(False), LeadStage.is_lost.is_(False)).limit(200))).all()
    for lead, stage in rows:
        lead.free_since, lead.work_due_at = t, None
        db.add(LeadEvent(lead_id=lead.id, at=t, kind="note", actor_id=None, meta={"free": True},
                         text=f"Лид свободен: на этапе «{stage.name}» с ним не поработали вовремя"))
        for uid in await crm_people(db, lead.branch_id, "crm"):
            await crm.alert(db, uid, "lead", f"Свободный лид: {lead.full_name}",
                            body=f"«{stage.name}». Кто первым поработает с лидом, тот станет ответственным",
                            link=f"/crm/leads/{lead.id}")
        out["freed"] += 1
    # (4) Paid an hour ago and still in no group: the branch admin is told on the screen, then once a day for a week.
    from app.services import retention

    paid = await crm.stage_by_code(db, "main", "paid")
    out["paid_no_group"] = 0
    if paid:
        in_group = select(GroupMember.id).where(GroupMember.student_id == Lead.student_id, GroupMember.left_on.is_(None)).exists()
        waiting = list(await db.scalars(select(Lead).where(
            Lead.stage_id == paid.id, Lead.archived_at.is_(None), Lead.stage_changed_at <= t - timedelta(hours=1),
            Lead.stage_changed_at > t - timedelta(days=7), ~in_group).limit(200)))
        for lead in waiting:
            if lead.student_id:
                st = await db.get(Student, lead.student_id)
                if st is None or st.archived_at is not None or st.status in (StudentStatus.LEFT, StudentStatus.FINISHED):
                    continue
            if not await once(f"paid-no-group:{lead.id}:{local(t).date()}", 2 * DAY):
                continue
            link = f"/students/{lead.student_id}" if lead.student_id else f"/crm/leads/{lead.id}"
            for uid in await retention.branch_admins(db, lead.branch_id):
                await crm.alert(db, uid, "lead", f"{lead.full_name} оплатил, но ещё не в группе",
                                body="Добавьте ученика в группу" if lead.student_id else "Создайте карточку ученика и добавьте в группу",
                                link=link)
            out["paid_no_group"] += 1
    hours = int(await setting(db, "lead_idle_hours") or 0)
    if hours and _day_time(t):
        has_note = select(LeadEvent.id).where(LeadEvent.lead_id == Lead.id, crm.manual_event()).exists()
        has_task = select(Task.id).where(Task.link_type == "lead", Task.link_id == Lead.id, Task.archived_at.is_(None),
                                         Task.status.not_in((TaskStatus.DONE, TaskStatus.CANCELLED))).exists()
        leads = list(await db.scalars(select(Lead).join(LeadStage, LeadStage.id == Lead.stage_id).where(
            Lead.archived_at.is_(None), Lead.free_since.is_(None), LeadStage.is_won.is_(False), LeadStage.is_lost.is_(False),
            Lead.created_at < t - timedelta(hours=hours), Lead.stage_changed_at < t - timedelta(hours=hours),
            ~has_note, ~has_task).order_by(Lead.id).limit(300)))
        per_user: dict[int, list[Lead]] = {}
        for lead in leads:
            if not await once(f"lead-idle:{lead.id}", 30 * DAY):
                continue
            for uid in [lead.assignee_id] if lead.assignee_id else await crm_people(db, lead.branch_id, "crm"):
                per_user.setdefault(uid, []).append(lead)
            out["idle"] += 1
        for uid, mine in per_user.items():
            if len(mine) > 3:  # a long list comes as one line, not as a flood
                await crm.alert(db, uid, "lead_stale", f"Лиды без заметки и задачи: {len(mine)}",
                                body="Поработайте с этими лидами и оставьте заметку", link="/crm")
                continue
            for lead in mine:
                await crm.alert(db, uid, "lead_stale", f"Поработайте с лидом: {lead.full_name}",
                                body=f"Больше {hours} ч без заметки и задачи", link=f"/crm/leads/{lead.id}")
    return out


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


async def complaint_deadlines(db: AsyncSession) -> int:
    """24 h to acknowledge, then the answer deadline: handlers are pinged once for each breach."""
    t = now()
    rows = await db.scalars(select(Complaint).where(Complaint.status.not_in(("answered", "closed")), or_(
        and_(Complaint.acknowledged_at.is_(None), Complaint.created_at < t - timedelta(hours=24)), Complaint.due_at < t)))
    sent = 0
    for c in rows:
        kind = "ack" if c.acknowledged_at is None and c.due_at >= t else "due"
        if not await once(f"complaint:{c.id}:{kind}:{int(c.due_at.timestamp())}", 30 * DAY):
            continue
        targets = await crm_people(db, c.branch_id, "complaints", "answer") if c.branch_id else []
        for uid in set(targets) - {c.against_user_id}:
            await notify_user(db, uid, "complaint", ("Жалоба без подтверждения 24 ч" if kind == "ack" else "Просрочен ответ на жалобу")
                              + f": {c.subject}", link=f"/complaints/{c.id}")
            sent += 1
    return sent


async def minutely(db: AsyncSession) -> dict:
    out = {"attendance": await attendance_reminders(db), "stale_leads": await stale_leads(db),
           "overdue_tasks": await overdue_tasks(db), "lead_control": await lead_control(db), "complaints": await complaint_deadlines(db)}
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


async def leave_followups(db: AsyncSession) -> int:
    """One-off, run by hand after the update that sends «ушёл» through the methodist: students whom staff already
    marked «ушёл» on the site without a reason get a task for the methodist. Safe to repeat."""
    from app.models import AuditLog, Role
    from app.models.identity import UserRole
    from app.services import retention

    owner = await db.scalar(select(UserRole.user_id).join(Role, Role.id == UserRole.role_id).where(Role.code == "owner").limit(1))
    manual = select(AuditLog.entity_id).where(AuditLog.entity == "student", AuditLog.action == "student.update",
                                              AuditLog.after["status"].astext == "left")
    n = 0
    for s in await db.scalars(select(Student).where(
            Student.archived_at.is_(None), Student.status == StudentStatus.LEFT, Student.leave_reason.is_(None),
            Student.id.in_(manual))):
        t = await retention.follow_up(
            db, s, "leave", f"Связаться с учеником: {s.full_name} отмечен как ушедший",
            "Ученику поставили статус «Ушёл» без причины. Свяжитесь с учеником или родителями и в карточке ученика "
            "нажмите «Решение»: ушёл (с причиной и когда может вернуться) или остаётся.", owner, hours=72)
        n += t is not None
    await db.commit()
    return n


async def close_left_members(db: AsyncSession) -> int:
    """One-off, run by hand after the update: students already «ушёл» who are still listed in a group leave it the
    day after they left, so they are no longer on the attendance list. Marked attendance is not touched. Safe to repeat."""
    from app.services import retention

    n = 0
    for s in await db.scalars(select(Student).where(
            Student.archived_at.is_(None), Student.status == StudentStatus.LEFT,
            exists().where(GroupMember.student_id == Student.id, GroupMember.left_on.is_(None)))):
        n += await retention.leave_groups(db, s, local(s.left_at).date() if s.left_at else today())
    await db.commit()
    return n


async def instagram_names(db: AsyncSession) -> int:
    """Instagram contacts saved without a name get the name and @username from their profile. Safe to repeat."""
    from app.models import ExternalContact, Lead
    from app.modules.inbox.service import NO_NAME
    from app.services import meta

    n = 0
    for c in await db.scalars(select(ExternalContact).where(
            ExternalContact.channel == "instagram", or_(ExternalContact.display_name.is_(None), ExternalContact.username.is_(None)))
            .order_by(ExternalContact.id.desc()).limit(200)):
        name, username = await meta.ig_profile(c.external_id)
        if not (name or username):
            continue
        c.username = c.username or username
        c.display_name = c.display_name or name or f"@{username}"
        lead = await db.get(Lead, c.lead_id) if c.lead_id else None
        if lead and lead.full_name == NO_NAME:
            lead.full_name = c.display_name
        n += 1
    await db.commit()
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


async def sync_freezes(db: AsyncSession) -> dict:
    """Status follows the freeze dates (QA B-5): a freeze that has started → «заморожен»; one that has ended or was
    cancelled → back to «учится». ends_on is the first day back."""
    d = today()
    running = and_(Freeze.student_id == Student.id, Freeze.starts_on <= d,
                   func.coalesce(Freeze.ended_early_on, Freeze.ends_on) > d)
    out = {"frozen": 0, "unfrozen": 0}
    for s in await db.scalars(select(Student).where(Student.archived_at.is_(None), Student.status.in_(StudentStatus.FREEZABLE),
                                                    exists().where(running)).with_for_update(skip_locked=True)):
        s.status = StudentStatus.FROZEN
        await write_audit(db, actor_id=None, action="student.freeze_started", entity="student", entity_id=s.id,
                          branch_id=s.branch_id)
        out["frozen"] += 1
    for s in await db.scalars(select(Student).where(Student.status == StudentStatus.FROZEN, ~exists().where(running))
                              .with_for_update(skip_locked=True)):
        in_group = await db.scalar(select(GroupMember.id).where(GroupMember.student_id == s.id, GroupMember.left_on.is_(None)).limit(1))
        s.status = StudentStatus.ACTIVE if in_group else StudentStatus.WAITING
        await write_audit(db, actor_id=None, action="student.freeze_ended", entity="student", entity_id=s.id,
                          branch_id=s.branch_id, note="Заморозка закончилась")
        out["unfrozen"] += 1
    return out


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


async def recurring_expenses(db: AsyncSession) -> int:
    """Regular expenses (rent, internet…) are booked automatically on their day of the month."""
    d = today()
    period = period_of(d)
    n = 0
    for tpl in await db.scalars(select(Expense).where(Expense.archived_at.is_(None), Expense.recurring.is_(True),
                                                      Expense.source_ref.is_(None))):
        if (tpl.recurring_day or tpl.spent_on.day) > d.day or period_of(tpl.spent_on) == period:
            continue
        ref = f"recurring:{tpl.id}:{period}"
        if await db.scalar(select(Expense.id).where(Expense.source_ref == ref)):
            continue
        db.add(Expense(branch_id=tpl.branch_id, category_id=tpl.category_id, amount=tpl.amount, spent_on=d, note=tpl.note,
                       source_ref=ref, created_by=tpl.created_by))
        n += 1
    return n


async def auto_coins(db: AsyncSession) -> int:
    """Birthday coins, and on the 1st — «месяц без пропусков» for the month that just ended."""
    d = today()
    n = 0
    for s in await db.scalars(select(Student).where(
            Student.archived_at.is_(None), Student.status == StudentStatus.ACTIVE,
            func.extract("month", Student.birth_date) == d.month, func.extract("day", Student.birth_date) == d.day)):
        n += await award_auto(db, s.id, "birthday", ("birthday", d.year), "С днём рождения!")
    if d.day == 1:
        prev_end = at_local(d, datetime.min.time())
        first = (d - timedelta(days=1)).replace(day=1)
        prev_start = at_local(first, datetime.min.time())
        rows = (await db.execute(
            select(Attendance.student_id, func.count(),
                   func.count().filter(Attendance.status.in_((AttendanceStatus.PRESENT, AttendanceStatus.LATE))))
            .join(Lesson, Lesson.id == Attendance.lesson_id)
            .where(Lesson.starts_at >= prev_start, Lesson.starts_at < prev_end, Attendance.student_id.is_not(None))
            .group_by(Attendance.student_id))).all()
        tag = first.year * 100 + first.month
        for sid, total, present in rows:
            if total >= 4 and total == present:
                n += await award_auto(db, sid, "perfect_month", ("month", tag), "Месяц без пропусков")
    return n


async def nightly(db: AsyncSession) -> dict:
    out = {"lessons": await extend_all(db), "tasks": await spawn_recurring_tasks(db)}
    await db.commit()
    out["freezes"] = await sync_freezes(db)
    out["left"] = await mark_left(db)
    out["blocked"] = await block_nonpayers(db)
    out["expenses"] = await recurring_expenses(db)
    out["coins"] = await auto_coins(db)
    from app.services.payroll import accrue_salaries
    out["salaries"] = await accrue_salaries(db)
    from app.services import meta
    out["instagram_token"] = await meta.ig_refresh()
    out["instagram_names"] = await instagram_names(db)
    await db.commit()
    return out


async def _run(job) -> dict:
    async with SessionLocal() as db:
        return await job(db)


async def loop() -> None:
    """Pushes every 5 s (ТЗ: push ≤ 1 min), minutely jobs every 60 s, nightly at 03:00 school time."""
    from app.services.push import push_pending

    last_night, last_minute = None, 0.0
    while True:
        try:
            await _run(push_pending)
            if time.monotonic() - last_minute >= 60:
                last_minute = time.monotonic()
                log.info("minutely %s", await _run(minutely))
            t = local(now())
            if t.hour == 3 and last_night != t.date():
                log.info("nightly %s", await _run(nightly))
                last_night = t.date()
        except Exception:
            log.exception("job failed")
        await asyncio.sleep(5)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    cmd = sys.argv[1] if len(sys.argv) > 1 else "loop"
    if cmd == "loop":
        asyncio.run(loop())
    else:
        print(asyncio.run(_run({"minutely": minutely, "nightly": nightly, "leave-followups": leave_followups,
                                 "close-left-members": close_left_members,
                                 "instagram-names": instagram_names,
                                 "book-lessons-preview": lambda db: bookpay.restore_lessons(db, commit=False),
                                 "book-lessons-fix": lambda db: bookpay.restore_lessons(db, commit=True)}[cmd])))
