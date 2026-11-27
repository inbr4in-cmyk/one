"""«Отчёты» (owner, 27.11.2026): the work of managers and of teachers over any days, for administrators.

Managers: a lead belongs to its responsible manager (or, with none, to who brought it in) — the same rule as the CRM
analytics. What happened in the period is counted by the day it happened (a stage move, a note, a payment)."""
from datetime import date, timedelta

from fastapi import APIRouter
from sqlalchemy import func, or_, select

from app.core.deps import DB, Actor, require
from app.models import Accrual, Attendance, Group, Lead, LeadEvent, LeadStage, Lesson, Payment, Pipeline, PlanItem, Task, TaskAssignee, User
from app.models.learning import AttendanceStatus, LessonStatus
from app.models.work import TaskStatus
from app.modules.finance.router import _branches, _xlsx
from app.services import crm
from app.services.clock import local_range, now, today

router = APIRouter(tags=["reports"])

# Administrators only (the owner and branch administrators hold students.archive), each inside his branches.
ADMIN = ("students", "archive")


def _days(date_from: date | None, date_to: date | None):
    d2 = date_to or today()
    d1 = date_from or d2.replace(day=1)
    if d1 > d2:
        d1, d2 = d2, d1
    if d2 - d1 > timedelta(days=366):
        d1 = d2 - timedelta(days=366)
    return d1, d2, *local_range(d1, d2)


def _pct(a: int, b: int) -> int | None:
    return round(100 * a / b) if b else None


async def _names(db, ids) -> dict[int, str]:
    ids = {i for i in ids if i}
    return dict((await db.execute(select(User.id, User.full_name).where(User.id.in_(ids)))).all()) if ids else {}


MANAGER_COLS = [("new", "Новые лиды"), ("worked", "Отработано лидов"), ("actions", "Звонки и заметки"),
                ("trial_booked", "Записал на пробный"), ("trial_done", "Пришли на пробный"), ("paid", "Оплатили"),
                ("lost", "Отказы"), ("conversion", "Конверсия, %"),
                ("tasks_done", "Задач выполнено"), ("tasks_overdue", "Просрочено задач"), ("sales", "Продаж"),
                ("sales_sum", "Сумма продаж, тг"), ("bonus", "Бонусы, тг")]


async def managers_data(db, actor: Actor, date_from, date_to, branch_id, manager_id) -> dict:
    d1, d2, start, end = _days(date_from, date_to)
    branches = _branches(actor, *ADMIN, branch_id)

    def br(col):
        return or_(col.in_(branches), col.is_(None)) if branches is not None else True

    rows: dict[int, dict] = {}

    def row(uid):
        return rows.setdefault(uid, {k: 0 for k, _ in MANAGER_COLS})

    who = func.coalesce(Lead.assignee_id, Lead.owner_id)
    main = await db.scalar(select(Pipeline.id).where(Pipeline.code == "main"))
    for uid, n in await db.execute(select(who, func.count()).where(br(Lead.branch_id), Lead.pipeline_id == main, Lead.created_at >= start,
                                                                   Lead.created_at < end).group_by(who)):
        if uid:
            row(uid)["new"] = n
    # what the manager did himself: notes, calls, meetings he wrote
    for uid, leads, n in await db.execute(
            select(LeadEvent.actor_id, func.count(func.distinct(LeadEvent.lead_id)), func.count())
            .join(Lead, Lead.id == LeadEvent.lead_id)
            .where(br(Lead.branch_id), crm.not_return(), crm.manual_event(), LeadEvent.at >= start, LeadEvent.at < end).group_by(LeadEvent.actor_id)):
        if uid:
            row(uid)["worked"], row(uid)["actions"] = leads, n
    # stage moves of the period go to the lead's manager; a lead moved twice to the same stage counts once
    stages = {s.id: s for s in await db.scalars(select(LeadStage))}
    pipes = dict((await db.execute(select(Pipeline.id, Pipeline.code))).all())
    seen = set()
    for lead_id, uid, meta in await db.execute(
            select(LeadEvent.lead_id, who, LeadEvent.meta).join(Lead, Lead.id == LeadEvent.lead_id)
            .where(br(Lead.branch_id), LeadEvent.kind == "stage", LeadEvent.at >= start, LeadEvent.at < end)):
        st = stages.get((meta or {}).get("to"))
        if not uid or st is None:
            continue
        pipe = pipes.get(st.pipeline_id)
        key = None
        if pipe == "main":
            key = "paid" if st.is_won else "lost" if st.is_lost else st.code if st.code in ("trial_booked", "trial_done") else None
        if key and (lead_id, key) not in seen:
            seen.add((lead_id, key))
            row(uid)[key] += 1
    lead_task = (Task.link_type == "lead", Task.archived_at.is_(None),
                 Task.link_id.not_in(select(Lead.id).join(Pipeline, Pipeline.id == Lead.pipeline_id).where(Pipeline.code == "return")))
    for uid, n in await db.execute(
            select(TaskAssignee.user_id, func.count()).join(Task, Task.id == TaskAssignee.task_id)
            .where(*lead_task, br(Task.branch_id), Task.status == TaskStatus.DONE, Task.done_at >= start, Task.done_at < end)
            .group_by(TaskAssignee.user_id)):
        row(uid)["tasks_done"] = n
    for uid, n in await db.execute(
            select(TaskAssignee.user_id, func.count()).join(Task, Task.id == TaskAssignee.task_id)
            .where(*lead_task, br(Task.branch_id), Task.status.not_in((TaskStatus.DONE, TaskStatus.CANCELLED)), Task.due_at < now())
            .group_by(TaskAssignee.user_id)):
        row(uid)["tasks_overdue"] = n
    seller = func.coalesce(Payment.seller_id, Payment.received_by)
    for uid, n, total in await db.execute(
            select(seller, func.count(), func.coalesce(func.sum(Payment.amount - Payment.refunded), 0))
            .where(br(Payment.branch_id), Payment.category == "course", Payment.paid_at >= start, Payment.paid_at < end).group_by(seller)):
        # a cashier who only takes money is not a manager: counted for those who also work leads
        if uid in rows:
            row(uid)["sales"], row(uid)["sales_sum"] = n, int(total)
    if rows:
        for uid, total in await db.execute(
                select(Accrual.user_id, func.coalesce(func.sum(Accrual.amount), 0))
                .where(Accrual.user_id.in_(rows), Accrual.kind.in_(("sale", "return", "trial_visit")),
                       Accrual.created_at >= start, Accrual.created_at < end).group_by(Accrual.user_id)):
            row(uid)["bonus"] = int(total)
    names = await _names(db, rows)
    out = []
    for uid, r in rows.items():
        r["conversion"] = _pct(r["paid"], r["new"])
        out.append({"user_id": uid, "name": names.get(uid) or "—", **r})
    out.sort(key=lambda r: (-r["new"], -r["worked"], r["name"]))
    people = [{"id": r["user_id"], "name": r["name"]} for r in sorted(out, key=lambda r: r["name"])]
    if manager_id:
        out = [r for r in out if r["user_id"] == manager_id]
    total = {k: sum(r[k] or 0 for r in out) for k, _ in MANAGER_COLS}
    total["conversion"] = _pct(total["paid"], total["new"])
    return {"period": [d1, d2], "rows": out, "total": total, "people": people}


TEACHER_COLS = [("planned", "Уроков по расписанию"), ("held", "Проведено"), ("held_pct", "Проведено, %"),
                ("not_marked", "Не отмечено"), ("cancelled", "Отменено"), ("subs", "Замены за других"),
                ("plan_pct", "По плану уровня, %"), ("attendance_pct", "Посещаемость, %"),
                ("pay_lessons", "За уроки, тг"), ("pay_other", "Бонусы, тг"), ("pay_total", "Итого, тг")]


async def teachers_data(db, actor: Actor, date_from, date_to, branch_id, teacher_id) -> dict:
    d1, d2, start, end = _days(date_from, date_to)
    branches = _branches(actor, *ADMIN, branch_id)
    br = Lesson.branch_id.in_(branches) if branches is not None else True
    teacher = func.coalesce(Lesson.actual_teacher_id, Lesson.teacher_id)
    in_days = (br, Lesson.starts_at >= start, Lesson.starts_at < end)
    planned_levels = set(await db.scalars(select(PlanItem.level_id).where(PlanItem.archived_at.is_(None)).distinct()))
    rows: dict[int, dict] = {}

    def row(uid):
        return rows.setdefault(uid, {**{k: 0 for k, _ in TEACHER_COLS}, "_plan_due": 0, "_plan": 0, "_came": 0, "_marks": 0})

    t = now()
    for x, kind in await db.execute(select(Lesson, Group.kind).outerjoin(Group, Group.id == Lesson.group_id).where(*in_days)):
        uid = x.actual_teacher_id or x.teacher_id
        if not uid:
            continue
        r = row(uid)
        if x.status == LessonStatus.CANCELLED:
            r["cancelled"] += 1
            continue
        r["planned"] += 1
        if x.actual_teacher_id and x.teacher_id and x.actual_teacher_id != x.teacher_id:
            r["subs"] += 1
        held = x.status == LessonStatus.DONE or x.attendance_marked_at is not None
        if held:
            r["held"] += 1
            # only an ordinary group goes by the level's plan lesson by lesson
            if kind == "group" and x.level_id in planned_levels and not x.is_support and not x.is_trial:
                r["_plan_due"] += 1
                r["_plan"] += x.plan_item_id is not None
        elif x.ends_at < t:
            r["not_marked"] += 1
    for uid, came, n in await db.execute(
            select(teacher, func.count().filter(Attendance.status.in_((AttendanceStatus.PRESENT, AttendanceStatus.LATE))), func.count())
            .join(Lesson, Lesson.id == Attendance.lesson_id)
            .where(*in_days, Attendance.student_id.is_not(None), Lesson.status != LessonStatus.CANCELLED).group_by(teacher)):
        if uid:
            row(uid)["_came"], row(uid)["_marks"] = came, n
    # pay for the lessons of these days (whenever it was counted), with later corrections of the same lessons
    for uid, total in await db.execute(
            select(Accrual.user_id, func.coalesce(func.sum(Accrual.amount), 0)).join(Lesson, Lesson.id == Accrual.ref_id)
            .where(Accrual.kind == "lesson", Accrual.ref_type == "lesson", *in_days).group_by(Accrual.user_id)):
        row(uid)["pay_lessons"] = int(total)
    ids = {f"lesson:{i}": i for i in await db.scalars(select(Lesson.id).where(*in_days))}
    if ids:
        for uid, total in await db.execute(
                select(Accrual.user_id, func.coalesce(func.sum(Accrual.amount), 0))
                .where(Accrual.kind == "correction", Accrual.ref_type.in_(ids)).group_by(Accrual.user_id)):
            row(uid)["pay_lessons"] += int(total)
    if rows:
        for uid, total in await db.execute(
                select(Accrual.user_id, func.coalesce(func.sum(Accrual.amount), 0))
                .where(Accrual.user_id.in_(rows), Accrual.kind.in_(("trial_retention", "final_test", "bonus", "deduction")),
                       Accrual.created_at >= start, Accrual.created_at < end).group_by(Accrual.user_id)):
            row(uid)["pay_other"] = int(total)
    names = await _names(db, rows)
    out = []
    for uid, r in rows.items():
        r["held_pct"] = _pct(r["held"], r["planned"])
        r["plan_pct"] = _pct(r.pop("_plan"), r.pop("_plan_due"))
        r["attendance_pct"] = _pct(r.pop("_came"), r.pop("_marks"))
        r["pay_total"] = r["pay_lessons"] + r["pay_other"]
        out.append({"user_id": uid, "name": names.get(uid) or "—", **r})
    out.sort(key=lambda r: r["name"])
    people = [{"id": r["user_id"], "name": r["name"]} for r in out]
    if teacher_id:
        out = [r for r in out if r["user_id"] == teacher_id]
    sums = ("planned", "held", "not_marked", "cancelled", "subs", "pay_lessons", "pay_other", "pay_total")
    total = {k: sum(r[k] for r in out) for k in sums}
    total["held_pct"] = _pct(total["held"], total["planned"])
    return {"period": [d1, d2], "rows": out, "total": total, "people": people}


@router.get("/reports/managers")
async def managers(db: DB, actor: Actor = require(*ADMIN), date_from: date | None = None, date_to: date | None = None,
                   branch_id: int | None = None, manager_id: int | None = None) -> dict:
    return await managers_data(db, actor, date_from, date_to, branch_id, manager_id)


@router.get("/reports/teachers")
async def teachers(db: DB, actor: Actor = require(*ADMIN), date_from: date | None = None, date_to: date | None = None,
                   branch_id: int | None = None, teacher_id: int | None = None) -> dict:
    return await teachers_data(db, actor, date_from, date_to, branch_id, teacher_id)


def _sheet(title: str, who: str, cols, data: dict, name: str):
    d1, d2 = data["period"]
    rows = [[r["name"], *[r[k] if r[k] is not None else "" for k, _ in cols]] for r in data["rows"]]
    return _xlsx(title, [who, *[label for _, label in cols]], rows, f"{name}-{d1}-{d2}.xlsx")


@router.get("/reports/managers.xlsx")
async def managers_xlsx(db: DB, actor: Actor = require(*ADMIN), date_from: date | None = None, date_to: date | None = None,
                        branch_id: int | None = None, manager_id: int | None = None):
    return _sheet("Менеджеры", "Менеджер", MANAGER_COLS,
                  await managers_data(db, actor, date_from, date_to, branch_id, manager_id), "managers")


@router.get("/reports/teachers.xlsx")
async def teachers_xlsx(db: DB, actor: Actor = require(*ADMIN), date_from: date | None = None, date_to: date | None = None,
                        branch_id: int | None = None, teacher_id: int | None = None):
    return _sheet("Учителя", "Учитель", TEACHER_COLS,
                  await teachers_data(db, actor, date_from, date_to, branch_id, teacher_id), "teachers")
