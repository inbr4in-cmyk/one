"""Payroll sheets, manual bonuses/deductions, approval and ratings (ТЗ 10)."""

from datetime import date, timedelta

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.core.audit import write_audit
from app.core.deps import DB, Actor, require
from app.core.errors import bad_request, conflict, not_found
from app.core.permissions import OWN
from app.core.schemas import In
from app.models import Accrual, Attendance, Expense, ExpenseCategory, Lesson, PayrollPeriod, StaffDay, StaffPayout, User, UserBranch
from app.models.learning import AttendanceStatus, LessonStatus
from app.modules.finance.router import month_bounds
from app.services.clock import now, period_of, today
from app.services.messaging import notify_user
from app.services.payroll import accrue_salary, month_days, norm_days, period_locked, TIMESHEET_FROM, WORK_WEEKDAYS, worked_days

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
    paid = dict((await db.execute(select(StaffPayout.user_id, func.sum(StaffPayout.amount)).where(
        StaffPayout.period == period, StaffPayout.cancelled_at.is_(None), StaffPayout.user_id.in_(list(people) or [0]))
        .group_by(StaffPayout.user_id))).all())
    for uid, p in people.items():
        p["paid"] = int(paid.get(uid, 0))
        p["left"] = p["total"] - p["paid"]
    branch_ids = {branch_id} if branch_id else ({a.branch_id for a in await db.scalars(
        select(Accrual).where(Accrual.period == period, *_scope_filter(actor, "view", None)))} - {None})
    done = {p.branch_id: p.status for p in await db.scalars(select(PayrollPeriod).where(
        PayrollPeriod.period == period, PayrollPeriod.branch_id.in_(branch_ids or {-1})))}
    statuses = {b: done.get(b, "draft") for b in sorted(branch_ids)}
    return {"period": period, "status": statuses, "people": sorted(people.values(), key=lambda p: -p["total"]),
            "total": sum(p["total"] for p in people.values())}


LESSON_SECTIONS = (("group", "Групповые уроки"), ("duo", "Дуэт"), ("individual", "Индивидуальные уроки"),
                   ("support", "Support-уроки"), ("club", "Открытые уроки"), ("room", "Уроки в кабинете с особой ставкой"),
                   ("level", "Уроки курса с особой ставкой"))


async def breakdown(db: DB, user_id: int, period: str, extra_filter: list) -> dict:
    """How one person's pay for the month is made up: lessons by format at the rate (ставка), the extra for
    students above the threshold separately (KPI), then everything else (оклад, премии, удержания…)."""
    from app.models import Group, Level, Room
    from app.services.clock import local
    from app.services.values import rate

    rows = (await db.execute(
        select(Accrual, Lesson, Group.kind, Room.teacher_rate, Level.teacher_rate).outerjoin(Lesson, (Accrual.ref_type == "lesson") & (Lesson.id == Accrual.ref_id))
        .outerjoin(Group, Group.id == Lesson.group_id).outerjoin(Room, Room.id == Lesson.room_id).outerjoin(Level, Level.id == Lesson.level_id)
        .where(Accrual.user_id == user_id, Accrual.period == period, *extra_filter).order_by(Accrual.id))).all()
    lessons = {k: {"key": k, "title": t, "count": 0, "amount": 0} for k, t in LESSON_SECTIONS}
    kpi = {"key": "kpi", "title": "KPI: доплата за учеников", "count": 0, "amount": 0}
    other: dict[str, dict] = {}
    bases: dict = {}
    for a, lesson, gkind, room_rate, level_rate in rows:
        if a.kind == "lesson" and lesson is not None:
            kind = "support" if lesson.is_support else (gkind or "group") if lesson.group_id else "individual"
            if room_rate and kind in ("group", "duo", "individual") and a.amount == room_rate:
                kind = "room"
            if level_rate and kind in ("group", "duo", "individual") and a.amount == level_rate:
                kind = "level"
            sec = lessons.get(kind) or lessons["group"]
            sec["count"] += 1
            if kind == "group":
                on = local(lesson.starts_at).date()
                if on not in bases:
                    bases[on] = await rate(db, "teacher_lesson_base", on)
                base = min(a.amount, bases[on])
                sec["amount"] += base
                if a.amount > base:
                    kpi["count"] += 1
                    kpi["amount"] += a.amount - base
            else:
                sec["amount"] += a.amount
        else:
            o = other.setdefault(a.kind, {"key": a.kind, "title": KIND_NAMES.get(a.kind, a.kind), "count": 0, "amount": 0})
            o["count"] += 1
            o["amount"] += a.amount
    rate_rows = [x for x in lessons.values() if x["count"]]
    return {"lessons": rate_rows, "lessons_total": sum(x["amount"] for x in rate_rows),
            "lessons_count": sum(x["count"] for x in rate_rows), "kpi": kpi,
            "other": list(other.values()), "total": sum(r[0].amount for r in rows)}


@router.get("/payroll/breakdown")
async def get_breakdown(user_id: int, db: DB, actor: Actor = require("payroll", "view"), period: str | None = None,
                        branch_id: int | None = None) -> dict:
    period = period or period_of(today())
    month_bounds(period)
    return await breakdown(db, user_id, period, _scope_filter(actor, "view", branch_id))


@router.get("/payroll/person")
async def person(user_id: int, db: DB, actor: Actor = require("payroll", "view"), period: str | None = None,
                 branch_id: int | None = None) -> dict:
    """The salary page of one staff member: every held lesson of the month by group and by day, then everything
    else (оклад, KPI, премии, удержания) line by line, and what was already paid out."""
    from app.models import Group, Level, Room
    from app.services.clock import local
    from app.services.values import rate

    period = period or period_of(today())
    month_bounds(period)
    flt = _scope_filter(actor, "view", branch_id)
    u = await db.get(User, user_id)
    if u is None:
        raise not_found("Сотрудник")
    rows = (await db.execute(
        select(Accrual, Lesson, Group, Room.teacher_rate, Level.teacher_rate).outerjoin(Lesson, (Accrual.ref_type == "lesson") & (Accrual.kind == "lesson") & (Lesson.id == Accrual.ref_id))
        .outerjoin(Group, Group.id == Lesson.group_id).outerjoin(Room, Room.id == Lesson.room_id).outerjoin(Level, Level.id == Lesson.level_id)
        .where(Accrual.user_id == user_id, Accrual.period == period, *flt).order_by(Accrual.id))).all()
    if not rows and actor.scope("payroll", "view") == OWN and user_id != actor.id:
        raise not_found("Сотрудник")
    groups: dict[str, dict] = {}
    other: list[dict] = []
    bases: dict = {}
    for a, lesson, g, room_rate, level_rate in rows:
        if a.kind == "lesson" and lesson is not None:
            kind = "support" if lesson.is_support else g.kind if g else "individual"
            key = f"g{g.id}" if g else kind
            name = g.name if g else ("Support-уроки" if lesson.is_support else "Индивидуальные уроки")
            sec = groups.setdefault(key, {"key": key, "group_id": g.id if g else None, "name": name, "kind": kind,
                                          "count": 0, "amount": 0, "base": 0, "kpi": 0, "lessons": []})
            at = local(lesson.starts_at)
            sec["count"] += 1
            sec["amount"] += a.amount
            # «Ставка» and «KPI» apart: in a group lesson the pay above the base rate is the extra for students
            base = a.amount
            if kind == "group" and not (room_rate and a.amount == room_rate) and not (level_rate and a.amount == level_rate):
                if at.date() not in bases:
                    bases[at.date()] = await rate(db, "teacher_lesson_base", at.date())
                base = min(a.amount, bases[at.date()])
            sec["base"] += base
            sec["kpi"] += a.amount - base
            sec["lessons"].append({"lesson_id": lesson.id, "day": at.day, "date": at.date().isoformat(), "time": f"{at:%H:%M}",
                                   "amount": a.amount, "base": base, "kpi": a.amount - base, "note": a.description})
        else:
            other.append({"id": a.id, "kind": a.kind, "title": KIND_NAMES.get(a.kind, a.kind), "amount": a.amount,
                          "description": a.description, "created_at": a.created_at.isoformat()})
    for sec in groups.values():
        sec["lessons"].sort(key=lambda x: (x["date"], x["time"]))
    total = sum(r[0].amount for r in rows)
    payouts = await _payout_list(db, user_id, period)
    paid = sum(b["total"] for b in payouts)
    lessons_total = sum(s["amount"] for s in groups.values())
    y, m = int(period[:4]), int(period[5:7])
    days = (date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1)).day
    return {"user": {"id": u.id, "full_name": u.full_name, "position": u.position, "pay_scheme": u.pay_scheme},
            "period": period, "days": days, "groups": sorted(groups.values(), key=lambda s: -s["amount"]),
            "lessons_total": lessons_total, "rate_total": sum(s["base"] for s in groups.values()),
            "kpi_total": sum(s["kpi"] for s in groups.values()), "lessons_count": sum(s["count"] for s in groups.values()),
            "other": other, "other_total": total - lessons_total, "total": total, "paid": paid, "left": total - paid,
            "payouts": payouts}


@router.get("/payroll/accruals", response_model=list[AccrualOut])
async def accruals(db: DB, actor: Actor = require("payroll", "view"), period: str | None = None,
                   user_id: int | None = None, branch_id: int | None = None) -> list[AccrualOut]:
    q = select(Accrual).where(Accrual.period == (period or period_of(today())), *_scope_filter(actor, "view", branch_id))
    if user_id:
        q = q.where(Accrual.user_id == user_id)
    return [_out(a) for a in await db.scalars(q.order_by(Accrual.id).limit(2000))]


# ---------- «Рассчитаться»: payouts ----------
PAYOUTS_FROM = "2026-11"  # earlier months were settled outside the program: nothing is carried over from them
PARTS = (("salary", "Оклад"), ("rate", "Ставка за уроки"), ("kpi", "KPI"), ("bonus", "Премия"),
         ("deduction", "Штраф"), ("carry", "Остаток с прошлых месяцев"))
KPI_KINDS = ("trial_retention", "final_test", "trial_visit", "return", "sale")


async def settlement(db: DB, user: User, period: str) -> dict:
    """What the person earned in the month by part of the pay, what was already handed out, what is left.
    «carry» is what is still owed from earlier months, or the debt when more was paid than earned."""
    bd = await breakdown(db, user.id, period, [])
    accrued = dict.fromkeys((k for k, _ in PARTS), 0)
    accrued["rate"] = bd["lessons_total"]
    accrued["kpi"] = bd["kpi"]["amount"]
    for o in bd["other"]:
        k = o["key"]
        accrued[k if k in ("salary", "bonus", "deduction") else "kpi" if k in KPI_KINDS else "rate"] += o["amount"]
    paid = {k: int(v) for k, v in (await db.execute(
        select(StaffPayout.part, func.sum(StaffPayout.amount)).where(
            StaffPayout.user_id == user.id, StaffPayout.period == period, StaffPayout.cancelled_at.is_(None))
        .group_by(StaffPayout.part))).all()}
    all_accrued = int(await db.scalar(select(func.coalesce(func.sum(Accrual.amount), 0)).where(
        Accrual.user_id == user.id, Accrual.period >= PAYOUTS_FROM, Accrual.period <= period)))
    all_paid = int(await db.scalar(select(func.coalesce(func.sum(StaffPayout.amount), 0)).where(
        StaffPayout.user_id == user.id, StaffPayout.period <= period, StaffPayout.cancelled_at.is_(None))))
    parts = []
    for k, title in PARTS:
        if k == "carry":
            continue
        parts.append({"part": k, "title": title, "accrued": accrued[k], "paid": paid.get(k, 0),
                      "left": accrued[k] - paid.get(k, 0), "note": None})
    balance = all_accrued - all_paid  # everything owed up to this month; negative = the person's debt
    carry = balance - sum(p["left"] for p in parts)
    parts.append({"part": "carry", "title": "Остаток с прошлых месяцев" if carry >= 0 else "Долг сотрудника",
                  "accrued": carry + paid.get("carry", 0), "paid": paid.get("carry", 0), "left": carry, "note": None})
    if user.pay_scheme in ("salary", "both") and user.salary and period >= TIMESHEET_FROM:
        worked, norm = await worked_days(db, user.id, period)
        parts[0]["note"] = f"{worked} из {norm} дн."
    return {"user_id": user.id, "full_name": user.full_name, "position": user.position, "period": period,
            "parts": parts, "balance": balance}


async def _payout_target(db: DB, actor: Actor, user_id: int, branch_id: int) -> User:
    actor.ensure_branch("payroll", "adjust", branch_id)
    if user_id == actor.id and not actor.is_owner:
        raise bad_request("С собой рассчитывается руководитель")
    target = await db.get(User, user_id)
    in_branch = await db.scalar(select(UserBranch.id).where(UserBranch.user_id == user_id, UserBranch.branch_id == branch_id))
    if target is None or target.kind != "staff" or in_branch is None:
        raise not_found("Сотрудник филиала")
    return target


async def _payout_list(db: DB, user_id: int, period: str | None) -> list[dict]:
    q = select(StaffPayout).where(StaffPayout.user_id == user_id, StaffPayout.cancelled_at.is_(None))
    if period:
        q = q.where(StaffPayout.period == period)
    batches: dict[int, dict] = {}
    names = dict(PARTS)
    for r in await db.scalars(q.order_by(StaffPayout.id.desc()).limit(500)):
        b = batches.setdefault(r.batch_id or r.id, {"id": r.batch_id or r.id, "period": r.period, "paid_on": r.paid_on.isoformat(),
                                                    "note": r.note, "total": 0, "lines": []})
        b["total"] += r.amount
        b["lines"].append({"part": r.part, "title": names.get(r.part, r.part), "amount": r.amount})
    return list(batches.values())


@router.get("/payroll/settlement")
async def get_settlement(user_id: int, branch_id: int, db: DB, actor: Actor = require("payroll", "adjust"),
                         period: str | None = None) -> dict:
    period = period or period_of(today())
    month_bounds(period)
    target = await _payout_target(db, actor, user_id, branch_id)
    out = await settlement(db, target, period)
    out["payouts"] = await _payout_list(db, user_id, period)
    return out


class PayLineIn(In):
    part: str = Field(pattern="^(salary|rate|kpi|bonus|deduction|carry)$")
    amount: int = Field(ge=-10_000_000, le=10_000_000)


class ExtraIn(In):
    amount: int = Field(gt=0, le=10_000_000)
    note: str = Field(min_length=3, max_length=255)


class PayoutIn(In):
    user_id: int
    branch_id: int
    period: str | None = Field(default=None, max_length=7)
    paid_on: date | None = None
    lines: list[PayLineIn] = Field(default_factory=list, max_length=6)
    # a new bonus or fine written and settled in the same payment
    bonus: ExtraIn | None = None
    fine: ExtraIn | None = None
    note: str | None = Field(default=None, max_length=255)


@router.post("/payroll/payouts", status_code=201)
async def pay_out(body: PayoutIn, db: DB, actor: Actor = require("payroll", "adjust")) -> dict:
    """Hand out the pay, whole or by part (only the salary, only the lesson rate…). More than earned may be paid:
    the difference stays as the person's debt. The money goes to the expenses, category «Зарплата»."""
    period = body.period or period_of(today())
    month_bounds(period)
    if period < PAYOUTS_FROM:
        raise bad_request("Расчёт ведётся с ноября 2026")
    target = await _payout_target(db, actor, body.user_id, body.branch_id)
    paid_on = body.paid_on or today()
    if paid_on > today() or paid_on < today() - timedelta(days=31):
        raise bad_request("Дата выплаты: сегодня или до 31 дня назад")
    lines = {}
    for ln in body.lines:
        if ln.amount == 0:
            continue
        if ln.part in lines:
            raise bad_request("Часть выплаты указана дважды")
        if ln.amount < 0 and ln.part not in ("deduction", "carry"):
            raise bad_request("Сумма выплаты не может быть меньше нуля")
        if ln.amount > 0 and ln.part == "deduction":
            raise bad_request("Штраф уменьшает выплату")
        lines[ln.part] = ln.amount
    for extra, kind, sign in ((body.bonus, "bonus", 1), (body.fine, "deduction", -1)):
        if extra is None:
            continue
        if await period_locked(db, period, body.branch_id):
            raise conflict("Ведомость за этот месяц уже утверждена: премию и штраф поставьте в текущем месяце")
        a = Accrual(user_id=target.id, branch_id=body.branch_id, period=period, kind=kind, amount=sign * extra.amount,
                    ref_type="manual", ref_id=None, description=extra.note, created_by=actor.id)
        db.add(a)
        await db.flush()
        await write_audit(db, actor_id=actor.id, action=f"payroll.{kind}", entity="accrual", entity_id=a.id,
                          branch_id=body.branch_id, ip=actor.ip,
                          after={"user_id": target.id, "amount": a.amount, "description": extra.note})
        lines[kind] = lines.get(kind, 0) + sign * extra.amount
    if not lines:
        raise bad_request("Укажите, что выплачиваете")
    total = sum(lines.values())
    if total < 0:
        raise bad_request("Штрафы и долг больше выплаты: выдавать нечего")
    names = dict(PARTS)
    expense = None
    if total > 0:
        cat = await db.scalar(select(ExpenseCategory.id).where(ExpenseCategory.code == "salary"))
        if cat is None:
            c = ExpenseCategory(code="salary", name="Зарплата")
            db.add(c)
            await db.flush()
            cat = c.id
        y, m = period.split("-")
        detail = ", ".join(f"{names[k].lower()} {v:,}".replace(",", " ") for k, v in lines.items())
        expense = Expense(branch_id=body.branch_id, category_id=cat, amount=total, spent_on=paid_on,
                          note=f"Зарплата: {target.full_name}, {m}.{y} ({detail})"[:255], created_by=actor.id)
        db.add(expense)
        await db.flush()
    rows = [StaffPayout(user_id=target.id, branch_id=body.branch_id, period=period, part=k, amount=v, paid_on=paid_on,
                        note=body.note, expense_id=expense.id if expense else None, created_by=actor.id)
            for k, v in lines.items()]
    db.add_all(rows)
    await db.flush()
    for r in rows:
        r.batch_id = rows[0].id
    if expense is not None:
        expense.source_ref = f"payout:{rows[0].id}"
    await write_audit(db, actor_id=actor.id, action="payroll.payout", entity="user", entity_id=target.id,
                      branch_id=body.branch_id, ip=actor.ip, after={"period": period, "lines": lines, "total": total,
                                                                   "paid_on": paid_on.isoformat()})
    await notify_user(db, target.id, "payroll", "Выплата", body=f"{total:,} тг".replace(",", " "), link="/payroll/my")
    await db.commit()
    out = await settlement(db, target, period)
    out["payouts"] = await _payout_list(db, target.id, period)
    return out


@router.post("/payroll/payouts/{batch_id}/cancel")
async def cancel_payout(batch_id: int, db: DB, actor: Actor = require("payroll", "adjust")) -> dict:
    """A payment entered by mistake: its lines and its expense are taken back (a bonus or fine written with it stays)."""
    rows = list(await db.scalars(select(StaffPayout).where(StaffPayout.batch_id == batch_id, StaffPayout.cancelled_at.is_(None))))
    if not rows:
        raise not_found("Выплата")
    actor.ensure_branch("payroll", "adjust", rows[0].branch_id)
    for r in rows:
        r.cancelled_at = now()
    if rows[0].expense_id:
        e = await db.get(Expense, rows[0].expense_id)
        if e is not None and e.archived_at is None:
            e.archived_at = now()
    await write_audit(db, actor_id=actor.id, action="payroll.payout_cancel", entity="user", entity_id=rows[0].user_id,
                      branch_id=rows[0].branch_id, ip=actor.ip, after={"batch_id": batch_id, "total": sum(r.amount for r in rows)})
    await db.commit()
    return {"ok": True}


@router.get("/payroll/my")
async def my_pay(db: DB, actor: Actor = require("payroll", "view"), period: str | None = None) -> dict:
    """«Мои начисления»: every staff member sees how their pay is formed, line by line."""
    period = period or period_of(today())
    items = [_out(a) for a in await db.scalars(select(Accrual).where(Accrual.user_id == actor.id, Accrual.period == period)
                                                 .order_by(Accrual.id))]
    salary = sum(i.amount for i in items if i.kind == "salary")
    paid = int(await db.scalar(select(func.coalesce(func.sum(StaffPayout.amount), 0)).where(
        StaffPayout.user_id == actor.id, StaffPayout.period == period, StaffPayout.cancelled_at.is_(None))))
    return {"period": period, "total": sum(i.amount for i in items), "salary_total": salary, "paid": paid,
            "payouts": await _payout_list(db, actor.id, period),
            "rates_total": sum(i.amount for i in items) - salary, "items": items,
            "breakdown": await breakdown(db, actor.id, period, [])}


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
