"""Expenses, P&L, owner dashboard and Excel exports (ТЗ 13)."""

import io
from datetime import date, time, timedelta

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from pydantic import Field
from sqlalchemy import func, select

from app.core.audit import write_audit
from app.core.deps import DB, Actor, require
from app.core.errors import bad_request, not_found
from app.core.query import paginate
from app.core.schemas import In, ORM, Page
from app.models import (
    Accrual, Attendance, Branch, Expense, ExpenseCategory, Lead, LeadStage, Lesson, Payment, Refund, Student, User,
)
from app.models.learning import AttendanceStatus, LessonStatus, StudentStatus
from app.services.clock import at_local, local, now, period_of, today

router = APIRouter(tags=["finance"])


def month_bounds(period: str):
    try:
        y, m = (int(x) for x in period.split("-"))
        start = date(y, m, 1)
    except ValueError as e:
        raise bad_request("Период в формате ГГГГ-ММ") from e
    end = date(y + (m == 12), m % 12 + 1, 1)
    return start, end, at_local(start, time(0)), at_local(end, time(0))


def _branches(actor: Actor, module: str, action: str, branch_id: int | None) -> set[int] | None:
    """Branches the report covers: the requested one (if allowed) or everything the actor may see."""
    allowed = actor.branches_for(module, action)
    if branch_id is not None:
        actor.ensure_branch(module, action, branch_id)
        return {branch_id}
    return allowed


# ---------- expenses ----------
class CategoryOut(ORM):
    id: int
    code: str
    name: str


class CategoryIn(In):
    name: str = Field(min_length=2, max_length=120)
    # Optional: generated when the category is added from the dictionaries page.
    code: str | None = Field(default=None, pattern=r"^[a-z0-9_]{2,32}$")


@router.get("/expense-categories", response_model=list[CategoryOut])
async def categories(db: DB, actor: Actor = require("finance", "view")) -> list:
    return list(await db.scalars(select(ExpenseCategory).where(ExpenseCategory.archived_at.is_(None)).order_by(ExpenseCategory.id)))


@router.post("/expense-categories", response_model=CategoryOut, status_code=201)
async def create_category(body: CategoryIn, db: DB, actor: Actor = require("finance", "edit")):
    if body.code and await db.scalar(select(ExpenseCategory).where(ExpenseCategory.code == body.code)):
        raise bad_request("Такой код уже есть")
    if await db.scalar(select(ExpenseCategory.id).where(func.lower(ExpenseCategory.name) == body.name.strip().lower(),
                                                        ExpenseCategory.archived_at.is_(None))):
        raise bad_request("Такая статья расхода уже есть")
    code = body.code or f"c{(await db.scalar(select(func.coalesce(func.max(ExpenseCategory.id), 0)))) + 1}"
    while await db.scalar(select(ExpenseCategory.id).where(ExpenseCategory.code == code)):
        code += "_"
    c = ExpenseCategory(name=body.name.strip(), code=code)
    db.add(c)
    await db.flush()
    await write_audit(db, actor_id=actor.id, action="expense_category.create", entity="expense_category", entity_id=c.id,
                      ip=actor.ip, after={"name": c.name})
    await db.commit()
    return c


class CategoryPatch(In):
    name: str = Field(min_length=2, max_length=120)


@router.patch("/expense-categories/{category_id}", response_model=CategoryOut)
async def rename_category(category_id: int, body: CategoryPatch, db: DB, actor: Actor = require("finance", "edit")):
    c = await db.get(ExpenseCategory, category_id)
    if c is None or c.archived_at is not None:
        raise not_found("Статья расхода")
    before = c.name
    c.name = body.name.strip()
    await write_audit(db, actor_id=actor.id, action="expense_category.update", entity="expense_category", entity_id=c.id,
                      ip=actor.ip, before={"name": before}, after={"name": c.name})
    await db.commit()
    return c


@router.post("/expense-categories/{category_id}/archive", status_code=204)
async def archive_category(category_id: int, db: DB, actor: Actor = require("finance", "edit")) -> None:
    """Archived, never deleted: past expenses keep their category in reports."""
    c = await db.get(ExpenseCategory, category_id)
    if c is None or c.archived_at is not None:
        raise not_found("Статья расхода")
    c.archived_at = now()
    await write_audit(db, actor_id=actor.id, action="expense_category.archive", entity="expense_category", entity_id=c.id,
                      ip=actor.ip, before={"name": c.name})
    await db.commit()


class ExpenseIn(In):
    branch_id: int | None = None  # None = shared network expense
    category_id: int
    amount: int = Field(gt=0, le=1_000_000_000)
    spent_on: date
    note: str | None = Field(default=None, max_length=255)
    receipt_url: str | None = Field(default=None, max_length=255)
    recurring: bool = False
    recurring_day: int | None = Field(default=None, ge=1, le=28)


class ExpenseOut(ORM):
    id: int
    branch_id: int | None
    category_id: int
    amount: int
    spent_on: date
    note: str | None
    receipt_url: str | None
    recurring: bool
    recurring_day: int | None
    source_ref: str | None
    created_by: int | None


def _check_expense_branch(actor: Actor, branch_id: int | None) -> None:
    if branch_id is None:
        if actor.branches_for("finance", "edit") is not None:
            raise bad_request("Общие расходы сети вносит только владелец")
    else:
        actor.ensure_branch("finance", "edit", branch_id)


@router.get("/expenses", response_model=Page[ExpenseOut])
async def list_expenses(db: DB, actor: Actor = require("finance", "view"), period: str | None = None,
                        branch_id: int | None = None, category_id: int | None = None,
                        limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)) -> Page:
    q = select(Expense).where(Expense.archived_at.is_(None))
    branches = _branches(actor, "finance", "view", branch_id)
    if branches is not None:
        q = q.where(Expense.branch_id.in_(branches) if branch_id else
                    (Expense.branch_id.in_(branches) | Expense.branch_id.is_(None)))
    if period:
        s, e, _, _ = month_bounds(period)
        q = q.where(Expense.spent_on >= s, Expense.spent_on < e)
    if category_id:
        q = q.where(Expense.category_id == category_id)
    rows, total = await paginate(db, q.order_by(Expense.spent_on.desc(), Expense.id.desc()), limit, offset)
    return Page(items=rows, total=total, limit=limit, offset=offset)


@router.post("/expenses", response_model=ExpenseOut, status_code=201)
async def create_expense(body: ExpenseIn, db: DB, actor: Actor = require("finance", "edit")):
    _check_expense_branch(actor, body.branch_id)
    if not await db.get(ExpenseCategory, body.category_id):
        raise not_found("Категория")
    e = Expense(**body.model_dump(), created_by=actor.id)
    db.add(e)
    await db.flush()
    await write_audit(db, actor_id=actor.id, action="expense.create", entity="expense", entity_id=e.id,
                      branch_id=e.branch_id, ip=actor.ip, after=body.model_dump(mode="json"))
    await db.commit()
    return e


@router.patch("/expenses/{expense_id}", response_model=ExpenseOut)
async def update_expense(expense_id: int, body: ExpenseIn, db: DB, actor: Actor = require("finance", "edit")):
    e = await db.get(Expense, expense_id)
    if e is None or e.archived_at:
        raise not_found("Расход")
    _check_expense_branch(actor, e.branch_id)
    _check_expense_branch(actor, body.branch_id)
    if e.source_ref:
        raise bad_request("Автоматический расход меняется в своём разделе")
    before = ExpenseOut.model_validate(e).model_dump(mode="json")
    for k, v in body.model_dump().items():
        setattr(e, k, v)
    await write_audit(db, actor_id=actor.id, action="expense.update", entity="expense", entity_id=e.id,
                      branch_id=e.branch_id, ip=actor.ip, before=before, after=body.model_dump(mode="json"))
    await db.commit()
    return e


@router.post("/expenses/{expense_id}/archive", status_code=204)
async def archive_expense(expense_id: int, db: DB, actor: Actor = require("finance", "edit")) -> None:
    e = await db.get(Expense, expense_id)
    if e is None or e.archived_at:
        raise not_found("Расход")
    _check_expense_branch(actor, e.branch_id)
    e.archived_at = now()
    await write_audit(db, actor_id=actor.id, action="expense.archive", entity="expense", entity_id=e.id,
                      branch_id=e.branch_id, ip=actor.ip)
    await db.commit()


# ---------- P&L ----------
async def pnl(db: DB, period: str, branches: set[int] | None) -> dict:
    """Revenue − refunds − expenses (own + share of network ones by revenue) − payroll accruals."""
    s, e, s_dt, e_dt = month_bounds(period)
    all_ids = list(await db.scalars(select(Branch.id).where(Branch.archived_at.is_(None)).order_by(Branch.id)))
    ids = [b for b in all_ids if branches is None or b in branches]
    names = {b.id: b.name for b in await db.scalars(select(Branch).where(Branch.id.in_(all_ids)))}

    rev = {(b, c): int(v) for b, c, v in (await db.execute(
        select(Payment.branch_id, Payment.category, func.sum(Payment.amount))
        .where(Payment.paid_at >= s_dt, Payment.paid_at < e_dt).group_by(Payment.branch_id, Payment.category))).all()}
    refunds = {b: int(v) for b, v in (await db.execute(
        select(Payment.branch_id, func.sum(Refund.amount)).join(Payment, Payment.id == Refund.payment_id)
        .where(Refund.created_at >= s_dt, Refund.created_at < e_dt).group_by(Payment.branch_id))).all()}
    cats = {c.id: c.name for c in await db.scalars(select(ExpenseCategory))}
    exp = (await db.execute(
        select(Expense.branch_id, Expense.category_id, func.sum(Expense.amount))
        .where(Expense.archived_at.is_(None), Expense.spent_on >= s, Expense.spent_on < e)
        .group_by(Expense.branch_id, Expense.category_id))).all()
    payroll = {b: int(v) for b, v in (await db.execute(
        select(Accrual.branch_id, func.sum(Accrual.amount)).where(Accrual.period == period)
        .group_by(Accrual.branch_id))).all()}

    revenue_by_branch = {b: sum(v for (bb, _), v in rev.items() if bb == b) for b in all_ids}
    total_rev = sum(revenue_by_branch.values())

    def share(b: int) -> float:
        return revenue_by_branch[b] / total_rev if total_rev else 1 / max(len(all_ids), 1)

    rows = []
    for b in ids:
        expenses: dict[str, int] = {}
        for bb, cid, v in exp:
            amt = int(v) if bb == b else round(int(v) * share(b)) if bb is None else 0
            if amt:
                expenses[cats.get(cid, "?")] = expenses.get(cats.get(cid, "?"), 0) + amt
        pay = payroll.get(b, 0) + (round(payroll.get(None, 0) * share(b)) if None in payroll else 0)
        revenue = {c: v for (bb, c), v in rev.items() if bb == b}
        gross = sum(revenue.values()) - refunds.get(b, 0)
        total_exp = sum(expenses.values()) + pay
        rows.append({"branch_id": b, "branch": names[b], "revenue": revenue, "refunds": refunds.get(b, 0),
                     "net_revenue": gross, "expenses": expenses, "payroll": pay, "total_expenses": total_exp,
                     "profit": gross - total_exp, "margin": round((gross - total_exp) / gross * 100, 1) if gross else None})
    tot = {k: sum(r[k] for r in rows) for k in ("refunds", "net_revenue", "payroll", "total_expenses", "profit")}
    tot["margin"] = round(tot["profit"] / tot["net_revenue"] * 100, 1) if tot["net_revenue"] else None
    return {"period": period, "branches": rows, "total": tot}


@router.get("/finance/pnl")
async def get_pnl(db: DB, actor: Actor = require("finance", "view"), period: str | None = None,
                  branch_id: int | None = None) -> dict:
    return await pnl(db, period or period_of(today()), _branches(actor, "finance", "view", branch_id))


# ---------- dashboard ----------
@router.get("/dashboard")
async def dashboard(db: DB, actor: Actor = require("dashboard", "view"), branch_id: int | None = None,
                    period: str | None = None) -> dict:
    branches = _branches(actor, "dashboard", "view", branch_id)

    def br(col):
        return col.in_(branches) if branches is not None else True

    d = today()
    if period and period != period_of(d):
        _, end, _, _ = month_bounds(period)
        d = end - timedelta(days=1)  # a past month: its last day stands in for "today"
    period = period_of(d)
    _, _, m_start, m_end = month_bounds(period)
    day_start = at_local(d, time(0))
    show_money = actor.can("finance", "view") or actor.can("payments", "view")
    out: dict = {"period": period}
    if show_money:
        out["revenue_today"] = int(await db.scalar(select(func.coalesce(func.sum(Payment.amount), 0)).where(
            br(Payment.branch_id), Payment.paid_at >= day_start)))
        out["revenue_month"] = int(await db.scalar(select(func.coalesce(func.sum(Payment.amount), 0)).where(
            br(Payment.branch_id), Payment.paid_at >= m_start, Payment.paid_at < m_end)))
        trend = []
        y, m = d.year, d.month
        for _ in range(6):
            p = f"{y:04d}-{m:02d}"
            _, _, a, b = month_bounds(p)
            trend.append({"period": p, "revenue": int(await db.scalar(select(func.coalesce(func.sum(Payment.amount), 0)).where(
                br(Payment.branch_id), Payment.paid_at >= a, Payment.paid_at < b)))})
            y, m = (y - 1, 12) if m == 1 else (y, m - 1)
        out["revenue_trend"] = list(reversed(trend))
        out["sales_month"] = await db.scalar(select(func.count()).select_from(Payment).where(
            br(Payment.branch_id), Payment.is_first.is_(True), Payment.paid_at >= m_start, Payment.paid_at < m_end))
    active = select(func.count()).select_from(Student).where(br(Student.branch_id), Student.archived_at.is_(None),
                                                             Student.status == StudentStatus.ACTIVE)
    out["students_active"] = await db.scalar(active)
    out["debtors"] = await db.scalar(active.where(Student.lessons_left <= 0))
    out["low_balance"] = await db.scalar(active.where(Student.lessons_left > 0, Student.lessons_left <= 2))
    out["lessons_today"] = await db.scalar(select(func.count()).select_from(Lesson).where(
        br(Lesson.branch_id), Lesson.starts_at >= day_start, Lesson.starts_at < day_start + timedelta(days=1),
        Lesson.status != LessonStatus.CANCELLED))
    att = (await db.execute(select(
        func.count(), func.count().filter(Attendance.status.in_((AttendanceStatus.PRESENT, AttendanceStatus.LATE))))
        .select_from(Attendance).join(Lesson, Lesson.id == Attendance.lesson_id)
        .where(br(Lesson.branch_id), Lesson.starts_at >= m_start, Lesson.starts_at < m_end, Attendance.student_id.is_not(None))
    )).one()
    out["attendance_rate"] = round(att[1] / att[0] * 100, 1) if att[0] else None
    if actor.can("crm", "view"):
        leads = select(func.count()).select_from(Lead).where(br(Lead.branch_id), Lead.created_at >= m_start,
                                                             Lead.created_at < m_end)
        new = await db.scalar(leads)
        won = await db.scalar(leads.join(LeadStage, LeadStage.id == Lead.stage_id).where(LeadStage.is_won.is_(True)))
        by_source = (await db.execute(select(Lead.source, func.count()).where(
            br(Lead.branch_id), Lead.created_at >= m_start, Lead.created_at < m_end).group_by(Lead.source))).all()
        out["leads_month"], out["conversion"] = new, round(won / new * 100, 1) if new else None
        out["leads_by_source"] = {s: c for s, c in by_source}
    return out


# ---------- export ----------
def _xlsx(title: str, header: list[str], rows: list[list], filename: str) -> StreamingResponse:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = title[:31]
    ws.append(header)
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="01225F")
    for r in rows:
        ws.append(r)
        # Values come from user input: a text starting with "=" must stay text, never become a formula.
        for c in ws[ws.max_row]:
            if isinstance(c.value, str) and c.value.startswith("="):
                c.data_type = "s"
    for col in ws.columns:
        ws.column_dimensions[col[0].column_letter].width = min(40, max(10, *(len(str(c.value or "")) + 2 for c in col)))
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/finance/export/payments.xlsx")
async def export_payments(db: DB, actor: Actor = require("finance", "export"), period: str = Query(...),
                          branch_id: int | None = None):
    branches = _branches(actor, "finance", "export", branch_id)
    _, _, a, b = month_bounds(period)
    q = (select(Payment, Student.full_name, User.full_name, Branch.name)
         .join(Student, Student.id == Payment.student_id).join(User, User.id == Payment.received_by)
         .join(Branch, Branch.id == Payment.branch_id)
         .where(Payment.paid_at >= a, Payment.paid_at < b).order_by(Payment.paid_at))
    if branches is not None:
        q = q.where(Payment.branch_id.in_(branches))
    rows = [[local(p.paid_at).strftime("%d.%m.%Y %H:%M"), br, st, p.category, p.lessons, p.lesson_price, p.discount, p.amount,
             p.refunded, p.method, by, "да" if p.is_first else ""] for p, st, by, br in (await db.execute(q)).all()]
    await write_audit(db, actor_id=actor.id, action="finance.export", entity="payments", ip=actor.ip,
                      note=f"{period} {sorted(branches) if branches else 'сеть'}")
    await db.commit()
    return _xlsx("Оплаты", ["Дата", "Филиал", "Ученик", "Категория", "Уроков", "Цена урока", "Скидка", "Сумма", "Возврат",
                            "Способ", "Принял", "Первая оплата"], rows, f"payments-{period}.xlsx")


@router.get("/finance/export/pnl.xlsx")
async def export_pnl(db: DB, actor: Actor = require("finance", "export"), period: str = Query(...),
                     branch_id: int | None = None):
    rep = await pnl(db, period, _branches(actor, "finance", "export", branch_id))
    rows: list[list] = []
    for r in rep["branches"]:
        rows.append([r["branch"], "Выручка", ""])
        rows += [["", c, v] for c, v in r["revenue"].items()]
        rows.append(["", "Возвраты", -r["refunds"]])
        rows += [["", f"Расход: {c}", -v] for c, v in r["expenses"].items()]
        rows.append(["", "Зарплата и бонусы", -r["payroll"]])
        rows.append(["", "Прибыль", r["profit"]])
    rows.append(["Итого по сети", "Прибыль", rep["total"]["profit"]])
    await write_audit(db, actor_id=actor.id, action="finance.export", entity="pnl", ip=actor.ip, note=period)
    await db.commit()
    return _xlsx(f"P&L {period}", ["Филиал", "Статья", "Сумма, тг"], rows, f"pnl-{period}.xlsx")

