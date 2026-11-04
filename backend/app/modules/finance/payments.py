"""Course sale and payments (ТЗ 5.2, 9.2, 13.1). Sales staff can't take payments: payments.create is not in their role."""

import re
from datetime import datetime, timedelta

from fastapi import APIRouter, Header, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.audit import write_audit
from app.core.deps import DB, Actor, require
from app.core.errors import bad_request, conflict, forbidden, not_found
from app.core.permissions import NETWORK
from app.core.schemas import In, ORM, Page
from app.models import Attendance, Lead, Lesson, Level, Payment, Refund, Student
from app.services.reversals import reverse_for_payment
from app.models.finance import PaymentMethod
from app.models.learning import AttendanceStatus, StudentStatus
from app.modules.students.scope import get_student_scoped
from app.services import balance as bal
from app.services import crm
from app.services.clock import local, local_range, now, parse_day
from app.services.messaging import notify_guardians
from app.services.payroll import accrue_once
from app.services.values import rate

router = APIRouter(tags=["payments"])


class PaymentIn(In):
    student_id: int = Field(ge=1)
    lessons: int = Field(ge=1, le=500)
    method: str = Field(max_length=16)
    discount: int = Field(default=0, ge=0, le=100_000_000)
    promo_code: str | None = Field(default=None, max_length=64)
    note: str | None = Field(default=None, max_length=255)
    level_id: int | None = Field(default=None, ge=1)


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
    student_lessons_left: int | None = None  # refund form: can't take back more lessons than are left


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


_IDEM_KEY = re.compile(r"^[A-Za-z0-9_\-:.]{8,64}$")
# Without an Idempotency-Key, the same payment by the same person within this window is treated as a double tap.
DOUBLE_TAP = timedelta(seconds=15)


def _out(p: Payment, s: Student) -> PaymentOut:
    out = PaymentOut.model_validate(p)
    out.student_name = s.full_name
    return out


async def _by_key(db: DB, key: str, actor: Actor, student_id: int) -> Payment | None:
    p = await db.scalar(select(Payment).where(Payment.idempotency_key == key))
    if p is not None and (p.received_by != actor.id or p.student_id != student_id):
        raise conflict("Этот ключ запроса уже использован для другой оплаты")
    return p


@router.post("/payments", response_model=PaymentOut, status_code=201)
async def take_payment(body: PaymentIn, db: DB, response: Response, actor: Actor = require("payments", "create"),
                       idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")) -> PaymentOut:
    """QA C-1: a repeated request (double tap, retry after a timeout) never takes the money twice.
    The client sends a fresh Idempotency-Key per payment form; a repeat with the same key returns the first payment (200)."""
    if body.method not in PaymentMethod.ALL:
        raise bad_request("Неизвестный способ оплаты")
    if idempotency_key is not None and not _IDEM_KEY.match(idempotency_key):
        raise bad_request("Некорректный заголовок Idempotency-Key")
    if idempotency_key and (done := await _by_key(db, idempotency_key, actor, body.student_id)):
        response.status_code = 200
        return _out(done, await db.get(Student, done.student_id))
    # The student row lock serializes payments for one student: the checks below see the previous one.
    s = await get_student_scoped(db, actor, body.student_id, "payments", "create", lock=True)
    actor.ensure_branch("payments", "create", s.branch_id)
    if idempotency_key and (done := await _by_key(db, idempotency_key, actor, s.id)):
        response.status_code = 200
        return _out(done, s)
    if not idempotency_key:
        recent = await db.scalar(select(Payment.id).where(
            Payment.student_id == s.id, Payment.received_by == actor.id, Payment.category == "course",
            Payment.lessons == body.lessons, Payment.method == body.method, Payment.paid_at > now() - DOUBLE_TAP))
        if recent:
            raise conflict("Такая оплата уже проведена только что. Обновите страницу")
    q, level = await _quote(db, s, body, actor)
    prior = await db.scalar(select(func.count()).select_from(Payment).where(Payment.student_id == s.id, Payment.category == "course"))
    was_left = s.status == StudentStatus.LEFT
    p = Payment(student_id=s.id, branch_id=s.branch_id, level_id=level.id, category="course", amount=q.to_pay,
                discount=q.discount, promo_code=body.promo_code, lessons=q.lessons, lesson_price=q.lesson_price,
                method=body.method, received_by=actor.id, paid_at=now(), is_first=prior == 0, note=body.note,
                idempotency_key=idempotency_key)
    try:
        async with db.begin_nested():
            db.add(p)
    except IntegrityError:
        # A parallel request with the same key won the race: answer with its payment.
        done = await _by_key(db, idempotency_key, actor, body.student_id) if idempotency_key else None
        if done is None:
            raise
        response.status_code = 200
        return _out(done, await db.get(Student, done.student_id))
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
    return _out(p, s)


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
async def list_payments(db: DB, actor: Actor = require("payments", "view"), student_id: int | None = Query(None, ge=1),
                        branch_id: int | None = Query(None, ge=1), date_from: str | None = Query(None, max_length=40),
                        date_to: str | None = Query(None, max_length=40), limit: int = Query(50, ge=1, le=200),
                        offset: int = Query(0, ge=0)) -> Page[PaymentOut]:
    """date_from / date_to are school-local calendar days, both inclusive (QA B-2): «today–today» is the whole day."""
    q = select(Payment, Student.full_name, Student.lessons_left).join(Student, Student.id == Payment.student_id)
    if actor.scope("payments", "view") != NETWORK:
        q = q.where(Payment.branch_id.in_(actor.branch_ids or {-1}))
    if student_id:
        q = q.where(Payment.student_id == student_id)
    if branch_id:
        q = q.where(Payment.branch_id == branch_id)
    start, end = local_range(parse_day(date_from), parse_day(date_to))
    if start:
        q = q.where(Payment.paid_at >= start)
    if end:
        q = q.where(Payment.paid_at < end)
    total = await db.scalar(select(func.count()).select_from(q.subquery()))
    rows = (await db.execute(q.order_by(Payment.id.desc()).limit(limit).offset(offset))).all()
    items = []
    for p, name, left in rows:
        o = PaymentOut.model_validate(p)
        o.student_name, o.student_lessons_left = name, left
        items.append(o)
    return Page(items=items, total=int(total or 0), limit=limit, offset=offset)


class RefundIn(In):
    lessons: int = Field(ge=0, le=10_000)
    amount: int = Field(ge=0, le=1_000_000_000)
    reason: str = Field(min_length=3, max_length=255)


async def _refunded_lessons(db: DB, payment_id: int) -> int:
    return int(await db.scalar(select(func.coalesce(func.sum(Refund.lessons_removed), 0)).where(Refund.payment_id == payment_id)))


async def lessons_left_from(db: DB, p: Payment, s: Student) -> int:
    """Lessons of this payment still on the balance. Lessons are spent oldest payment first, so the newest
    payments hold what is left: this payment keeps whatever the later ones don't cover."""
    own = p.lessons - await _refunded_lessons(db, p.id)
    later = 0
    for q_id, q_lessons in (await db.execute(select(Payment.id, Payment.lessons).where(
            Payment.student_id == s.id, Payment.category == "course", Payment.id > p.id))).all():
        later += max(q_lessons - await _refunded_lessons(db, q_id), 0)
    return max(0, min(own, s.lessons_left - later))


@router.get("/payments/{payment_id}/refundable")
async def refundable(payment_id: int, db: DB, actor: Actor = require("payments", "refund")) -> dict:
    """Limits for the refund form."""
    p = await db.get(Payment, payment_id)
    if p is None:
        raise not_found("Оплата")
    actor.ensure_branch("payments", "refund", p.branch_id)
    s = await db.get(Student, p.student_id)
    left = await lessons_left_from(db, p, s) if p.lessons else 0
    money_left = p.amount - p.refunded
    return {"lessons_max": left, "amount_max": _amount_cap(p, left, money_left, await _refunded_lessons(db, p.id)) if p.lessons
            else money_left, "amount_left": money_left}


def _amount_cap(p: Payment, lessons: int, money_left: int, refunded_lessons: int) -> int:
    """Money that matches `lessons` of this payment: their share of what was paid; taking every remaining lesson
    of the payment allows the whole remaining amount (no rounding leftovers)."""
    if lessons >= p.lessons - refunded_lessons:
        return money_left
    return min(money_left, -(-p.amount * lessons // p.lessons))


@router.post("/payments/{payment_id}/refund", status_code=201)
async def refund(payment_id: int, body: RefundIn, db: DB, actor: Actor = require("payments", "refund")) -> dict:
    """QA B-3: a refund takes back at most the lessons left from this payment and the money matching them.
    0 lessons and 0 tenge is not a refund. Bonuses for the sale are reversed in full on a full refund, in proportion otherwise."""
    p = await db.get(Payment, payment_id, with_for_update=True, populate_existing=True)
    if p is None:
        raise not_found("Оплата")
    actor.ensure_branch("payments", "refund", p.branch_id)
    s = await db.get(Student, p.student_id, with_for_update=True, populate_existing=True)
    if body.lessons == 0 and body.amount == 0:
        raise bad_request("Укажите сумму или уроки для возврата")
    money_left = p.amount - p.refunded
    if body.amount > money_left:
        raise bad_request(f"Сумма возврата больше оплаченной: можно вернуть не больше {money_left} ₸")
    if p.lessons:
        refunded_lessons = await _refunded_lessons(db, p.id)
        left = await lessons_left_from(db, p, s)
        if body.lessons > left:
            raise bad_request(f"По этой оплате осталось только {left} ур.")
        if body.lessons == 0:
            raise bad_request("Возврат денег без уроков невозможен: укажите, сколько уроков списать")
        cap = _amount_cap(p, body.lessons, money_left, refunded_lessons)
        if body.amount > cap:
            raise bad_request(f"За {body.lessons} ур. можно вернуть не больше {cap} ₸")
    elif body.lessons:
        raise bad_request("В этой оплате нет уроков")
    r = Refund(payment_id=p.id, amount=body.amount, lessons_removed=body.lessons, reason=body.reason, created_by=actor.id)
    db.add(r)
    await db.flush()
    p.refunded += body.amount
    if body.lessons:
        await bal.apply(db, s, "refund", lessons=-body.lessons, price=p.lesson_price, ref=("refund", r.id), actor_id=actor.id,
                        note=f"Возврат: {body.reason}")
    # ТЗ 10.5: bonuses tied to this sale are cancelled — fully on a full refund, in proportion on a partial one.
    if p.amount > 0:
        share = (p.refunded, p.amount)
    else:  # paid entirely from the money balance: the lessons tell how much was given back
        share = (await _refunded_lessons(db, p.id), p.lessons or 1)
    reversed_ = await reverse_for_payment(db, p, s, actor.id, share=share, refund_id=r.id)
    await write_audit(db, actor_id=actor.id, action="payment.refund", entity="payment", entity_id=p.id, branch_id=p.branch_id,
                      ip=actor.ip, after={"amount": body.amount, "lessons": body.lessons, "reason": body.reason,
                                          "bonuses_reversed": reversed_, "full": share[0] >= share[1]})
    await db.commit()
    return {"refund_id": r.id, "bonuses_reversed": reversed_, "full": share[0] >= share[1]}
