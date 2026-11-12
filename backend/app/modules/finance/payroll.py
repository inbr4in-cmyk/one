"""Payroll sheets, manual bonuses/deductions, approval and ratings (ТЗ 10)."""

from datetime import date

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.core.audit import write_audit
from app.core.deps import DB, Actor, require
from app.core.errors import bad_request, conflict, not_found
from app.core.permissions import OWN
from app.core.schemas import In
from app.models import Accrual, Attendance, Lesson, PayrollPeriod, StaffDay, User, UserBranch
from app.models.learning import AttendanceStatus, LessonStatus
from app.modules.finance.router import month_bounds
from app.services.clock import now, period_of, today
from app.services.messaging import notify_user
from app.services.payroll import accrue_salary, month_days, norm_days, period_locked, TIMESHEET_FROM, WORK_WEEKDAYS

router = APIRouter(tags=["payroll"])

KIND_NAMES = {
    "lesson": "Уроки", "trial_retention": "Удержание после пробного", "final_test": "Финальный тест",
    "trial_visit": "Пришёл на пробный", "return": "Возврат ученика", "sale": "Продажа курса", "salary": "Оклад",
    "bonus": "Премия", "deduction": "Удержание", "reversal": "Сторно", "correction": "Исправление",
}


class AccrualOut(BaseModel):
    id: int
    user_id: int
    branch_id: int | None
    period: str
    kind: str
    amount: int
    description: str
    ref_type: str | None
    ref_id: int | None
    created_by: int | None
    created_at: str


def _out(a: Accrual) -> AccrualOut:
    return AccrualOut(id=a.id, user_id=a.user_id, branch_id=a.branch_id, period=a.period, kind=a.kind, amount=a.amount,
                      description=a.description, ref_type=a.ref_type, ref_id=a.ref_id, created_by=a.created_by,
                      created_at=a.created_at.isoformat())


def _scope_filter(actor: Actor, action: str, branch_id: int | None):
    """Own scope → only my accruals; branch → accruals of my branches; network → all."""
    s = actor.scope("payroll", action)
    conds = []
    if s == OWN:
        conds.append(Accrual.user_id == actor.id)
    else:
        allowed = actor.branches_for("payroll", action)
        if allowed is not None:
            conds.append(Accrual.branch_id.in_(allowed))
    if branch_id is not None:
        if s != OWN:
            actor.ensure_branch("payroll", action, branch_id)
        conds.append(Accrual.branch_id == branch_id)
    return conds


@router.get("/payroll")
async def sheet(db: DB, actor: Actor = require("payroll", "view"), period: str | None = None,
                branch_id: int | None = None) -> dict:
    period = period or period_of(today())
    month_bounds(period)
    rows = (await db.execute(
        select(Accrual.user_id, Accrual.kind, func.sum(Accrual.amount), func.count())
        .where(Accrual.period == period, *_scope_filter(actor, "view", branch_id))
        .group_by(Accrual.user_id, Accrual.kind))).all()
    users = {u.id: u for u in await db.scalars(select(User).where(User.id.in_({r[0] for r in rows})))} if rows else {}
    people: dict[int, dict] = {}
    for uid, kind, total, cnt in rows:
        u = users.get(uid)
        p = people.setdefault(uid, {"user_id": uid, "full_name": u.full_name if u else "?", "position": u.position if u else None,
                                    "pay_scheme": u.pay_scheme if u else None, "by_kind": {}, "total": 0, "rates_total": 0,
                                    "salary_total": 0})
        p["by_kind"][kind] = {"title": KIND_NAMES.get(kind, kind), "amount": int(total), "count": cnt}
        p["total"] += int(total)
        p["salary_total" if kind == "salary" else "rates_total"] += int(total)
    branch_ids = {branch_id} if branch_id else ({a.branch_id for a in await db.scalars(
        select(Accrual).where(Accrual.period == period, *_scope_filter(actor, "view", None)))} - {None})
    done = {p.branch_id: p.status for p in await db.scalars(select(PayrollPeriod).where(
        PayrollPeriod.period == period, PayrollPeriod.branch_id.in_(branch_ids or {-1})))}
    statuses = {b: done.get(b, "draft") for b in sorted(branch_ids)}
    return {"period": period, "status": statuses, "people": sorted(people.values(), key=lambda p: -p["total"]),
            "total": sum(p["total"] for p in people.values())}


@router.get("/payroll/accruals", response_model=list[AccrualOut])
async def accruals(db: DB, actor: Actor = require("payroll", "view"), period: str | None = None,
                   user_id: int | None = None, branch_id: int | None = None) -> list[AccrualOut]:
    q = select(Accrual).where(Accrual.period == (period or period_of(today())), *_scope_filter(actor, "view", branch_id))
    if user_id:
        q = q.where(Accrual.user_id == user_id)
    return [_out(a) for a in await db.scalars(q.order_by(Accrual.id).limit(2000))]


@router.get("/payroll/my")
async def my_pay(db: DB, actor: Actor = require("payroll", "view"), period: str | None = None) -> dict:
    """«Мои начисления»: every staff member sees how their pay is formed, line by line."""
    period = period or period_of(today())
    items = [_out(a) for a in await db.scalars(select(Accrual).where(Accrual.user_id == actor.id, Accrual.period == period)
                                                 .order_by(Accrual.id))]
    salary = sum(i.amount for i in items if i.kind == "salary")
    return {"period": period, "total": sum(i.amount for i in items), "salary_total": salary,
            "rates_total": sum(i.amount for i in items) - salary, "items": items}


class AdjustIn(In):
    user_id: int
    branch_id: int
    kind: str = Field(pattern="^(bonus|deduction|salary)$")
    amount: int = Field(gt=0, le=10_000_000)
    description: str = Field(min_length=3, max_length=255)
    period: str | None = Field(default=None, max_length=255)


@router.post("/payroll/adjust", response_model=AccrualOut, status_code=201)
async def adjust(body: AdjustIn, db: DB, actor: Actor = require("payroll", "adjust")) -> AccrualOut:
    actor.ensure_branch("payroll", "adjust", body.branch_id)
    if body.user_id == actor.id and not actor.is_owner:
        raise bad_request("Себе премии и удержания ставит руководитель")
    target = await db.get(User, body.user_id)
    in_branch = await db.scalar(select(UserBranch).where(UserBranch.user_id == body.user_id, UserBranch.branch_id == body.branch_id))
    if target is None or target.kind != "staff" or in_branch is None:
        raise not_found("Сотрудник филиала")
    period = body.period or period_of(today())
    month_bounds(period)
    if await period_locked(db, period, body.branch_id):
        raise conflict("Ведомость за этот месяц уже утверждена")
    a = Accrual(user_id=body.user_id, branch_id=body.branch_id, period=period, kind=body.kind,
                amount=-body.amount if body.kind == "deduction" else body.amount, ref_type="manual", ref_id=None,
                description=body.description, created_by=actor.id)
    db.add(a)
    await db.flush()
    await write_audit(db, actor_id=actor.id, action=f"payroll.{body.kind}", entity="accrual", entity_id=a.id,
                      branch_id=body.branch_id, ip=actor.ip, after={"user_id": body.user_id, "amount": a.amount,
                                                                   "description": body.description})
    await notify_user(db, body.user_id, "payroll", "Премия" if a.amount > 0 else "Удержание",
                      body=f"{a.amount:+,} тг: {body.description}".replace(",", " "), link="/payroll/my")
    await db.commit()
    return _out(a)


class PeriodIn(In):
    period: str = Field(max_length=255)
    branch_id: int


async def _period(db: DB, body: PeriodIn) -> PayrollPeriod:
    month_bounds(body.period)
    p = await db.scalar(select(PayrollPeriod).where(PayrollPeriod.period == body.period, PayrollPeriod.branch_id == body.branch_id))
    if p is None:
        p = PayrollPeriod(period=body.period, branch_id=body.branch_id, status="draft")
        db.add(p)
        await db.flush()
    return p


@router.post("/payroll/periods/approve")
async def approve(body: PeriodIn, db: DB, actor: Actor = require("payroll", "approve")) -> dict:
    """After approval the sheet is frozen: later corrections go into the next month (ТЗ 10.5)."""
    actor.ensure_branch("payroll", "approve", body.branch_id)
    if body.period >= period_of(today()):
        raise bad_request("Утвердить можно только закончившийся месяц")
    p = await _period(db, body)
    if p.status != "draft":
        raise conflict("Ведомость уже утверждена")
    p.status, p.approved_by, p.approved_at = "approved", actor.id, now()
    total = await db.scalar(select(func.coalesce(func.sum(Accrual.amount), 0)).where(
        Accrual.period == body.period, Accrual.branch_id == body.branch_id))
    await write_audit(db, actor_id=actor.id, action="payroll.approve", entity="payroll_period", entity_id=p.id,
                      branch_id=body.branch_id, ip=actor.ip, after={"period": body.period, "total": int(total)})
    for uid in set(await db.scalars(select(Accrual.user_id).where(Accrual.period == body.period,
                                                                    Accrual.branch_id == body.branch_id))):
        await notify_user(db, uid, "payroll", f"Ведомость за {body.period} утверждена", link="/payroll/my")
    await db.commit()
    return {"period": p.period, "branch_id": p.branch_id, "status": p.status, "total": int(total)}


@router.post("/payroll/periods/paid")
async def mark_paid(body: PeriodIn, db: DB, actor: Actor = require("payroll", "approve")) -> dict:
    actor.ensure_branch("payroll", "approve", body.branch_id)
    p = await _period(db, body)
    if p.status != "approved":
        raise conflict("Сначала утвердите ведомость")
    p.status = "paid"
    await write_audit(db, actor_id=actor.id, action="payroll.paid", entity="payroll_period", entity_id=p.id,
                      branch_id=body.branch_id, ip=actor.ip)
    await db.commit()
    return {"period": p.period, "branch_id": p.branch_id, "status": p.status}


@router.get("/payroll/ratings")
async def ratings(db: DB, actor: Actor = require("dashboard", "view"), period: str | None = None,
                  branch_id: int | None = None) -> dict:
    """Teacher rating: lessons held, average class size, attendance; sales rating: trial visits, sales, returns."""
    period = period or period_of(today())
    _, _, a, b = month_bounds(period)
    branches = actor.branches_for("dashboard", "view")
    if branch_id is not None:
        actor.ensure_branch("dashboard", "view", branch_id)
        branches = {branch_id}
    teacher = func.coalesce(Lesson.actual_teacher_id, Lesson.teacher_id)
    q = (select(teacher, func.count(func.distinct(Lesson.id)), func.count(Attendance.id),
                func.count(Attendance.id).filter(Attendance.status.in_((AttendanceStatus.PRESENT, AttendanceStatus.LATE))))
         .select_from(Lesson).outerjoin(Attendance, (Attendance.lesson_id == Lesson.id) & Attendance.student_id.is_not(None))
         .where(Lesson.status == LessonStatus.DONE, Lesson.starts_at >= a, Lesson.starts_at < b).group_by(teacher))
    if branches is not None:
        q = q.where(Lesson.branch_id.in_(branches))
    t_rows = (await db.execute(q)).all()
    s_q = (select(Accrual.user_id, Accrual.kind, func.count())
           .where(Accrual.period == period, Accrual.kind.in_(("trial_visit", "sale", "return", "trial_retention")))
           .group_by(Accrual.user_id, Accrual.kind))
    if branches is not None:
        s_q = s_q.where(Accrual.branch_id.in_(branches))
    s_rows = (await db.execute(s_q)).all()
    ids = {r[0] for r in t_rows} | {r[0] for r in s_rows}
    names = {u.id: u.full_name for u in await db.scalars(select(User).where(User.id.in_(ids)))} if ids else {}
    teachers = [{"user_id": uid, "full_name": names.get(uid), "lessons": n, "marks": marks,
                 "attendance_rate": round(present / marks * 100, 1) if marks else None,
                 "avg_students": round(present / n, 1) if n else 0} for uid, n, marks, present in t_rows]
    teachers.sort(key=lambda r: (-(r["attendance_rate"] or 0), -r["lessons"]))
    sales: dict[int, dict] = {}
    for uid, kind, cnt in s_rows:
        sales.setdefault(uid, {"user_id": uid, "full_name": names.get(uid)})[kind] = cnt
    return {"period": period, "teachers": teachers,
            "sales": sorted(sales.values(), key=lambda r: -(r.get("sale", 0) + r.get("trial_visit", 0) + r.get("return", 0)))}


# ---------- табель (staff timesheet) ----------
DAY_STATUSES = ("work", "off", "sick", "vacation", "absent")


async def _branch_staff(db: DB, branch_id: int) -> list[User]:
    return list(await db.scalars(
        select(User).join(UserBranch, UserBranch.user_id == User.id)
        .where(UserBranch.branch_id == branch_id, User.kind == "staff", User.archived_at.is_(None), User.is_active.is_(True))
        .order_by(User.full_name)))


@router.get("/payroll/timesheet")
async def timesheet(branch_id: int, db: DB, actor: Actor = require("payroll", "view"), period: str | None = None) -> dict:
    """The month's timesheet of a branch: every staff member × every day. Salaried staff see their pay by days."""
    period = period or period_of(today())
    month_bounds(period)
    own = actor.scope("payroll", "view") == OWN
    if not own:
        actor.ensure_branch("payroll", "view", branch_id)
    days = month_days(period)
    people = await _branch_staff(db, branch_id)
    if own:
        people = [u for u in people if u.id == actor.id]
    marks = (await db.execute(select(StaffDay.user_id, StaffDay.day, StaffDay.status).where(
        StaffDay.user_id.in_([u.id for u in people] or [0]), StaffDay.day >= days[0], StaffDay.day <= days[-1]))).all()
    by_user: dict[int, dict[str, str]] = {}
    for uid, d, st in marks:
        by_user.setdefault(uid, {})[d.isoformat()] = st
    norm = norm_days(period)
    see_salary = actor.can("payroll", "adjust") or not own
    out = []
    for u in people:
        m = by_user.get(u.id, {})
        worked = sum(1 for v in m.values() if v == "work")
        salaried = u.pay_scheme in ("salary", "both") and u.salary > 0
        out.append({"user_id": u.id, "full_name": u.full_name, "position": u.position, "pay_scheme": u.pay_scheme,
                    "salary": u.salary if see_salary or u.id == actor.id else None, "days": m, "worked": worked,
                    "amount": round(u.salary * worked / norm) if salaried and norm and period >= TIMESHEET_FROM else None})
    return {"period": period, "branch_id": branch_id, "norm": norm, "workdays": list(WORK_WEEKDAYS),
            "locked": await period_locked(db, period, branch_id), "can_edit": actor.can("payroll", "adjust"),
            "people": out}


class DayIn(In):
    user_id: int
    branch_id: int
    days: list[date] = Field(min_length=1, max_length=31)
    status: str | None = Field(default=None, pattern="^(work|off|sick|vacation|absent)$")


@router.put("/payroll/timesheet")
async def set_days(body: DayIn, db: DB, actor: Actor = require("payroll", "adjust")) -> dict:
    """Branch admin marks one or several days of a staff member (status null clears the day)."""
    actor.ensure_branch("payroll", "adjust", body.branch_id)
    if not await db.scalar(select(UserBranch.id).where(UserBranch.user_id == body.user_id, UserBranch.branch_id == body.branch_id)):
        raise not_found("Сотрудник филиала")
    periods = {period_of(d) for d in body.days}
    if len(periods) != 1:
        raise bad_request("Дни одного месяца")
    period = periods.pop()
    if await period_locked(db, period, body.branch_id):
        raise conflict("Ведомость за этот месяц уже утверждена")
    if body.status == "work" and max(body.days) > today():
        raise bad_request("Рабочий день отмечается в тот же день или позже")
    existing = {x.day: x for x in await db.scalars(select(StaffDay).where(StaffDay.user_id == body.user_id,
                                                                          StaffDay.day.in_(body.days)))}
    for d in set(body.days):
        x = existing.get(d)
        if body.status is None:
            if x is not None:
                await db.delete(x)
        elif x is None:
            db.add(StaffDay(user_id=body.user_id, branch_id=body.branch_id, day=d, status=body.status, created_by=actor.id))
        else:
            x.status, x.branch_id, x.created_by = body.status, body.branch_id, actor.id
    await db.flush()
    u = await db.get(User, body.user_id)
    await accrue_salary(db, u, period)
    await write_audit(db, actor_id=actor.id, action="timesheet.set", entity="user", entity_id=body.user_id,
                      branch_id=body.branch_id, ip=actor.ip,
                      after={"days": sorted(d.isoformat() for d in body.days), "status": body.status})
    await db.commit()
    return {"ok": True}
