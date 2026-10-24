"""Course sale and payments (ТЗ 5.2, 9.2, 13.1). Sales staff can't take payments: payments.create is not in their role."""

from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.core.audit import write_audit
from app.core.deps import DB, Actor, require
from app.core.errors import bad_request, forbidden, not_found
from app.core.permissions import NETWORK
from app.core.query import paginate
from app.core.schemas import ORM, Page
from app.models import Attendance, Lead, Lesson, Level, Payment, Refund, Student
from app.services.reversals import reverse_for_payment
from app.models.finance import PaymentMethod
from app.models.learning import AttendanceStatus, StudentStatus
from app.modules.students.scope import get_student_scoped
from app.services import balance as bal
from app.services import crm
from app.services.clock import local, now
from app.services.messaging import notify_guardians
from app.services.payroll import accrue_once
from app.services.values import rate

router = APIRouter(tags=["payments"])


class PaymentIn(BaseModel):
    student_id: int
    lessons: int = Field(ge=1, le=500)
    method: str
    discount: int = Field(default=0, ge=0)
    promo_code: str | None = None
    note: str | None = Field(default=None, max_length=255)
    level_id: int | None = None


class PaymentOut(ORM):
    id: int
    student_id: int
    branch_id: int
    level_id: int | None
    category: str
    amount: int
    discount: int
    lessons: int
    lesson_price: int
    method: str
    received_by: int
    paid_at: datetime
    refunded: int
    is_first: bool
    note: str | None
    student_name: str | None = None


class PaymentQuote(BaseModel):
    lessons: int
    lesson_price: int
    gross: int
    discount: int
    money_balance_used: int
    to_pay: int


async def _quote(db: DB, s: Student, body: PaymentIn, actor: Actor) -> tuple[PaymentQuote, Level]:
    level = await db.get(Level, body.level_id or s.level_id) if (body.level_id or s.level_id) else None
    if level is None:
        raise bad_request("У ученика не указан уровень")
    if body.level_id and s.level_id and body.level_id != s.level_id and not actor.can("payments", "discount"):
        # Paying at another level's price is a discount in disguise; only the next level is allowed (moving up).
        current = await db.get(Level, s.level_id)
        if current is None or current.next_level_id != body.level_id:
            raise forbidden("Оплата по цене другого уровня — только у сотрудников с правом на скидки")
    if body.discount and not actor.can("payments", "discount"):
        raise forbidden("Скидки — только у сотрудников с правом")
    gross = body.lessons * level.lesson_price
    if body.discount > gross:
        raise bad_request("Скидка больше суммы")
    # Money left from a level transfer counts toward the next payment (ТЗ 5.3).
    used = min(max(s.money_balance, 0), gross - body.discount)
    return PaymentQuote(lessons=body.lessons, lesson_price=level.lesson_price, gross=gross, discount=body.discount,
                        money_balance_used=used, to_pay=gross - body.discount - used), level


@router.post("/payments/quote", response_model=PaymentQuote)
async def quote(body: PaymentIn, db: DB, actor: Actor = require("payments", "create")) -> PaymentQuote:
    s = await get_student_scoped(db, actor, body.student_id, "payments", "create")
    return (await _quote(db, s, body, actor))[0]


@router.post("/payments", response_model=PaymentOut, status_code=201)
async def take_payment(body: PaymentIn, db: DB, actor: Actor = require("payments", "create")) -> PaymentOut:
    if body.method not in PaymentMethod.ALL:
        raise bad_request("Неизвестный способ оплаты")
    s = await get_student_scoped(db, actor, body.student_id, "payments", "create", lock=True)
    actor.ensure_branch("payments", "create", s.branch_id)
    q, level = await _quote(db, s, body, actor)
    prior = await db.scalar(select(func.count()).select_from(Payment).where(Payment.student_id == s.id, Payment.category == "course"))
    was_left = s.status == StudentStatus.LEFT
    p = Payment(student_id=s.id, branch_id=s.branch_id, level_id=level.id, category="course", amount=q.to_pay,
                discount=q.discount, promo_code=body.promo_code, lessons=q.lessons, lesson_price=q.lesson_price,
                method=body.method, received_by=actor.id, paid_at=now(), is_first=prior == 0, note=body.note)
    db.add(p)
    await db.flush()
    await bal.apply(db, s, "payment", lessons=q.lessons, money=-q.money_balance_used, price=q.lesson_price,
                    ref=("payment", p.id), actor_id=actor.id, note=f"Оплата {q.lessons} × {q.lesson_price}")
    s.last_payment_at = p.paid_at
    s.access_blocked_at = None
    if s.status in (StudentStatus.LEAD, StudentStatus.TRIAL, StudentStatus.LEFT, StudentStatus.FINISHED):
        s.status = StudentStatus.ACTIVE
    if not s.office_user_id:
        s.office_user_id = actor.id
    await _sale_facts(db, s, p, actor, was_left)
    await notify_guardians(db, s, "payment", {"amount": f"{p.amount:,}".replace(",", " "), "what": f"обучение ({level.name})",
                                              "lessons": q.lessons, "left": s.lessons_left}, ref=("payment", p.id))
    await write_audit(db, actor_id=actor.id, action="payment.create", entity="payment", entity_id=p.id, branch_id=p.branch_id,
                      ip=actor.ip, after={"student_id": s.id, "amount": p.amount, "lessons": p.lessons, "method": p.method,
                                          "discount": p.discount})
    await db.commit()
    out = PaymentOut.model_validate(p)
    out.student_name = s.full_name
    return out


async def _sale_facts(db: DB, s: Student, p: Payment, actor: Actor, was_left: bool) -> None:
    """First payment of a lead → «Оплатил», office manager's sale bonus, trial teacher's retention bonus;
    a «Возврат» lead paying → return bonus for the sales person (ТЗ 9.2, 9.3, 10)."""
    lead = await db.get(Lead, s.lead_id) if s.lead_id else None
    if lead is None:
        return
    d = local(p.paid_at).date()
    paid_stage = await crm.stage_by_code(db, "return" if was_left else "main", "paid")
    if paid_stage and lead.stage_id != paid_stage.id:
        await crm.move(db, lead, paid_stage, actor.id, f"Оплата {p.amount} тг")
    if was_left and lead.owner_id:
        await accrue_once(db, user_id=lead.owner_id, kind="return", amount=await rate(db, "sales_return", d), ref=("lead", lead.id),
                          on=d, branch_id=s.branch_id, description=f"Возврат ученика: {s.full_name}", created_by=actor.id)
        return
    if not p.is_first or not lead.trial_lesson_id:
        return
    trial = await db.get(Lesson, lead.trial_lesson_id)
    attended = await db.scalar(select(Attendance.id).where(
        Attendance.lesson_id == lead.trial_lesson_id, Attendance.lead_id == lead.id,
        Attendance.status.in_((AttendanceStatus.PRESENT, AttendanceStatus.LATE))))
    if trial is None or attended is None:
        return
    await accrue_once(db, user_id=actor.id, kind="sale", amount=await rate(db, "office_sale", d), ref=("payment", p.id), on=d,
                      branch_id=s.branch_id, description=f"Продажа после пробного: {s.full_name}", created_by=actor.id)
    await accrue_once(db, user_id=trial.actual_teacher_id or trial.teacher_id, kind="trial_retention",
                      amount=await rate(db, "teacher_trial_retention", d), ref=("lead", lead.id), on=d,
                      branch_id=s.branch_id, description=f"Удержание после пробного: {s.full_name}", created_by=actor.id)


@router.get("/payments", response_model=Page[PaymentOut])
async def list_payments(db: DB, actor: Actor = require("payments", "view"), student_id: int | None = None,
                        branch_id: int | None = None, date_from: datetime | None = None, date_to: datetime | None = None,
                        limit: int = 50, offset: int = 0) -> Page[PaymentOut]:
    q = select(Payment, Student.full_name).join(Student, Student.id == Payment.student_id)
    if actor.scope("payments", "view") != NETWORK:
        q = q.where(Payment.branch_id.in_(actor.branch_ids or {-1}))
    if student_id:
        q = q.where(Payment.student_id == student_id)
    if branch_id:
        q = q.where(Payment.branch_id == branch_id)
    if date_from:
        q = q.where(Payment.paid_at >= date_from)
    if date_to:
        q = q.where(Payment.paid_at < date_to)
    total = await db.scalar(select(func.count()).select_from(q.subquery()))
    rows = (await db.execute(q.order_by(Payment.id.desc()).limit(min(limit, 200)).offset(offset))).all()
    items = []
    for p, name in rows:
        o = PaymentOut.model_validate(p)
        o.student_name = name
        items.append(o)
    _ = paginate  # list uses a join, paginated by hand
    return Page(items=items, total=int(total or 0), limit=limit, offset=offset)


class RefundIn(BaseModel):
    lessons: int = Field(ge=0)
    amount: int = Field(ge=0)
    reason: str = Field(min_length=3, max_length=255)


@router.post("/payments/{payment_id}/refund", status_code=201)
async def refund(payment_id: int, body: RefundIn, db: DB, actor: Actor = require("payments", "refund")) -> dict:
    p = await db.get(Payment, payment_id, with_for_update=True, populate_existing=True)
    if p is None:
        raise not_found("Оплата")
    actor.ensure_branch("payments", "refund", p.branch_id)
    s = await db.get(Student, p.student_id, with_for_update=True, populate_existing=True)
    if body.amount > p.amount - p.refunded:
        raise bad_request("Сумма возврата больше оплаченной")
    if body.lessons > s.lessons_left:
        raise bad_request(f"У ученика осталось только {s.lessons_left} уроков")
    r = Refund(payment_id=p.id, amount=body.amount, lessons_removed=body.lessons, reason=body.reason, created_by=actor.id)
    db.add(r)
    await db.flush()
    p.refunded += body.amount
    if body.lessons:
        await bal.apply(db, s, "refund", lessons=-body.lessons, price=p.lesson_price, ref=("refund", r.id), actor_id=actor.id,
                        note=f"Возврат: {body.reason}")
    # ТЗ 10.5: bonuses tied to this sale are cancelled.
    reversed_ = await reverse_for_payment(db, p, s, actor.id)
    await write_audit(db, actor_id=actor.id, action="payment.refund", entity="payment", entity_id=p.id, branch_id=p.branch_id,
                      ip=actor.ip, after={"amount": body.amount, "lessons": body.lessons, "reason": body.reason,
                                          "bonuses_reversed": reversed_})
    await db.commit()
    return {"refund_id": r.id, "bonuses_reversed": reversed_}
