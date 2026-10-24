"""Test builder, public QR placement test (ТЗ 6) and final level tests (ТЗ 5.5)."""

import hashlib
import hmac

import jwt
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.audit import write_audit
from app.core.config import get_settings
from app.core.deps import DB, Actor, CurrentActor, require
from app.core.errors import bad_request, forbidden, not_found
from app.core.ratelimit import client_ip, hit
from app.core.schemas import ORM
from app.core.security import create_purpose_token, decode_purpose_token, normalize_phone
from app.models import Attempt, Branch, Group, GroupMember, Lead, LeadEvent, Level, Question, Student, Test
from app.models.crm import LeadSource
from app.modules.crm.service import create_lead, crm_people, find_by_phone
from app.modules.students.scope import get_student_scoped
from app.services.clock import now
from app.services.coins import award_auto
from app.services.messaging import notify_user
from app.services.payroll import accrue_once
from app.services.values import rate

router = APIRouter(tags=["tests"])


# ---------- scoring ----------
def score(questions: list[Question], answers: dict) -> tuple[int, bool]:
    """Returns (auto score, needs manual review). Answers: {question_id: [option indexes] | "text"}."""
    total, manual = 0, False
    for q in questions:
        a = answers.get(str(q.id))
        if q.kind == "text":
            manual = manual or bool(a)
            continue
        picked = sorted(set(a)) if isinstance(a, list) else ([a] if isinstance(a, int) else [])
        if picked and picked == sorted(set(q.correct or [])):
            total += q.points
    return total, manual


def recommend(test: Test, value: int) -> int | None:
    best = None
    for row in sorted(test.scale or [], key=lambda r: r.get("min", 0)):
        if value >= int(row.get("min", 0)):
            best = row.get("level_id")
    return best


# ---------- builder ----------
class TestIn(BaseModel):
    kind: str = Field(pattern="^(placement|final|training)$")
    title: str = Field(min_length=2, max_length=255)
    level_id: int | None = None
    max_score: int = Field(default=150, ge=1, le=1000)
    pass_score: int | None = None
    time_limit_min: int | None = Field(default=None, ge=1, le=300)
    scale: list[dict] = []
    is_published: bool = False


class TestOut(ORM):
    id: int
    kind: str
    title: str
    level_id: int | None
    max_score: int
    pass_score: int | None
    time_limit_min: int | None
    scale: list | dict
    is_published: bool
    questions: int = 0


class QuestionIn(BaseModel):
    order: int = 0
    kind: str = Field(default="single", pattern="^(single|multi|text)$")
    text: str = Field(min_length=1, max_length=2000)
    options: list[str] = []
    correct: list[int] = []
    points: int = Field(default=1, ge=0, le=150)


class QuestionOut(ORM):
    id: int
    order: int
    kind: str
    text: str
    options: list | dict
    correct: list | dict
    points: int


@router.get("/tests", response_model=list[TestOut])
async def list_tests(db: DB, actor: Actor = require("tests", "view"), kind: str | None = None) -> list[TestOut]:
    q = select(Test).where(Test.archived_at.is_(None))
    if kind:
        q = q.where(Test.kind == kind)
    out = []
    for t in await db.scalars(q.order_by(Test.kind, Test.id)):
        o = TestOut.model_validate(t)
        o.questions = len((await db.scalars(select(Question.id).where(Question.test_id == t.id, Question.archived_at.is_(None)))).all())
        out.append(o)
    return out


@router.post("/tests", response_model=TestOut, status_code=201)
async def create_test(body: TestIn, db: DB, actor: Actor = require("tests", "edit")) -> TestOut:
    t = Test(**body.model_dump())
    db.add(t)
    await db.flush()
    await write_audit(db, actor_id=actor.id, action="test.create", entity="test", entity_id=t.id, ip=actor.ip)
    await db.commit()
    return TestOut.model_validate(t)


@router.put("/tests/{test_id}", response_model=TestOut)
async def update_test(test_id: int, body: TestIn, db: DB, actor: Actor = require("tests", "edit")) -> TestOut:
    t = await db.get(Test, test_id)
    if t is None:
        raise not_found("Тест")
    for k, v in body.model_dump().items():
        setattr(t, k, v)
    await write_audit(db, actor_id=actor.id, action="test.update", entity="test", entity_id=t.id, ip=actor.ip)
    await db.commit()
    return TestOut.model_validate(t)


@router.get("/tests/{test_id}/questions", response_model=list[QuestionOut])
async def questions(test_id: int, db: DB, actor: Actor = require("tests", "edit")) -> list[QuestionOut]:
    rows = await db.scalars(select(Question).where(Question.test_id == test_id, Question.archived_at.is_(None)).order_by(Question.order, Question.id))
    return [QuestionOut.model_validate(q) for q in rows]


@router.post("/tests/{test_id}/questions", response_model=QuestionOut, status_code=201)
async def add_question(test_id: int, body: QuestionIn, db: DB, actor: Actor = require("tests", "edit")) -> QuestionOut:
    if await db.get(Test, test_id) is None:
        raise not_found("Тест")
    if body.kind != "text" and (len(body.options) < 2 or not body.correct or max(body.correct) >= len(body.options)):
        raise bad_request("Нужны минимум 2 варианта и правильный ответ")
    q = Question(test_id=test_id, **body.model_dump())
    db.add(q)
    await db.commit()
    return QuestionOut.model_validate(q)


@router.put("/questions/{question_id}", response_model=QuestionOut)
async def update_question(question_id: int, body: QuestionIn, db: DB, actor: Actor = require("tests", "edit")) -> QuestionOut:
    q = await db.get(Question, question_id)
    if q is None:
        raise not_found("Вопрос")
    for k, v in body.model_dump().items():
        setattr(q, k, v)
    await db.commit()
    return QuestionOut.model_validate(q)


@router.post("/questions/{question_id}/archive", status_code=204)
async def archive_question(question_id: int, db: DB, actor: Actor = require("tests", "edit")) -> None:
    q = await db.get(Question, question_id)
    if q is None:
        raise not_found("Вопрос")
    q.archived_at = now()
    await db.commit()


# ---------- QR placement test (public, no login) ----------
def qr_token(branch_id: int) -> str:
    sig = hmac.new(get_settings().jwt_secret.encode(), f"qr:{branch_id}".encode(), hashlib.sha256).hexdigest()[:16]
    return f"{branch_id}-{sig}"


def branch_from_token(token: str) -> int:
    try:
        bid = int(token.split("-", 1)[0])
    except ValueError:
        raise not_found("Ссылка") from None
    if not hmac.compare_digest(qr_token(bid), token):
        raise not_found("Ссылка")
    return bid


@router.get("/branches/{branch_id}/qr")
async def branch_qr(branch_id: int, request: Request, actor: Actor = require("tests", "view")) -> dict:
    token = qr_token(branch_id)
    return {"token": token, "path": f"/t/{token}"}


class PublicQuestion(BaseModel):
    id: int
    kind: str
    text: str
    options: list


async def _placement(db: DB) -> Test:
    t = await db.scalar(select(Test).where(Test.kind == "placement", Test.is_published.is_(True), Test.archived_at.is_(None))
                        .order_by(Test.id.desc()))
    if t is None:
        raise not_found("Тест")
    return t


@router.get("/public/placement/{token}")
async def public_test(token: str, db: DB) -> dict:
    bid = branch_from_token(token)
    branch = await db.get(Branch, bid)
    t = await _placement(db)
    qs = await db.scalars(select(Question).where(Question.test_id == t.id, Question.archived_at.is_(None)).order_by(Question.order, Question.id))
    # Correct answers never leave the server.
    return {"branch": branch.name if branch else "", "title": t.title, "time_limit_min": t.time_limit_min,
            "questions": [PublicQuestion(id=q.id, kind=q.kind, text=q.text, options=q.options or []).model_dump() for q in qs]}


class StartIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    phone: str = Field(min_length=10, max_length=20)
    age: int | None = Field(default=None, ge=3, le=99)
    parent_name: str | None = Field(default=None, max_length=120)
    parent_phone: str | None = Field(default=None, max_length=20)
    consent: bool


@router.post("/public/placement/{token}/start")
async def start(token: str, body: StartIn, request: Request, db: DB) -> dict:
    await hit(f"placement:{client_ip(request)}", 10, 3600)
    if not body.consent:
        raise bad_request("Нужно согласие на обработку персональных данных")
    bid = branch_from_token(token)
    t = await _placement(db)
    phone = normalize_phone(body.phone)
    if len(phone) != 12 or not phone.startswith("+7"):
        raise bad_request("Укажите казахстанский номер +7")
    a = Attempt(test_id=t.id, branch_id=bid, taker_name=body.name, taker_phone=phone, started_at=now(),
                answers={"_meta": {"age": body.age, "parent_name": body.parent_name,
                                   "parent_phone": normalize_phone(body.parent_phone) if body.parent_phone else None}})
    db.add(a)
    await db.commit()
    return {"attempt_id": a.id, "attempt_token": create_purpose_token(a.id, "attempt", minutes=90)}


class SubmitIn(BaseModel):
    attempt_token: str
    answers: dict


@router.post("/public/placement/submit")
async def submit(body: SubmitIn, request: Request, db: DB) -> dict:
    await hit(f"placement-submit:{client_ip(request)}", 20, 3600)
    try:
        attempt_id = decode_purpose_token(body.attempt_token, "attempt")
    except jwt.PyJWTError:
        raise HTTPException(401, "Время теста истекло, начните заново") from None
    a = await db.get(Attempt, attempt_id)
    if a is None or a.status != "in_progress":
        raise bad_request("Тест уже завершён")
    t = await db.get(Test, a.test_id)
    qs = list(await db.scalars(select(Question).where(Question.test_id == t.id, Question.archived_at.is_(None))))
    auto, _ = score(qs, body.answers)
    meta_ = (a.answers or {}).get("_meta", {})
    a.answers = {**{k: v for k, v in body.answers.items() if k.isdigit()}, "_meta": meta_}
    a.auto_score = a.score = auto
    a.status, a.finished_at = "done", now()
    a.recommended_level_id = recommend(t, auto)
    level = await db.get(Level, a.recommended_level_id) if a.recommended_level_id else None
    # ТЗ 6: attach to the existing lead by phone, otherwise create a lead from the QR test.
    lead = await find_by_phone(db, a.taker_phone) or (await find_by_phone(db, meta_.get("parent_phone")) if meta_.get("parent_phone") else None)
    if lead is None:
        lead = await create_lead(db, full_name=a.taker_name, phone=a.taker_phone, branch_id=a.branch_id, source=LeadSource.QR,
                                 owner_id=None, age=meta_.get("age"), parent_name=meta_.get("parent_name"),
                                 parent_phone=meta_.get("parent_phone"))
    lead.placement_score, lead.level_id = auto, a.recommended_level_id
    lead.last_activity_at = now()
    a.lead_id = lead.id
    db.add(LeadEvent(lead_id=lead.id, at=now(), kind="test", text=f"Тест уровня: {auto} баллов → {level.name if level else '—'}",
                     actor_id=None, meta={"attempt_id": a.id}))
    if lead.assignee_id:
        await notify_user(db, lead.assignee_id, "lead", f"{lead.full_name} прошёл тест уровня: {level.name if level else auto}",
                          link=f"/crm/leads/{lead.id}")
    await db.commit()
    return {"score": auto, "max": t.max_score, "level": level.name if level else None}


# ---------- final tests (ТЗ 5.5) ----------
class ResultIn(BaseModel):
    student_id: int
    answers: dict | None = None
    manual_score: int | None = Field(default=None, ge=0)


class AttemptOut(ORM):
    id: int
    test_id: int
    student_id: int | None
    lead_id: int | None
    auto_score: int
    manual_score: int | None
    score: int
    status: str
    recommended_level_id: int | None


async def finalize_final(db: DB, a: Attempt, t: Test, actor_id: int | None) -> None:
    """> 100 of 150 → 1 000 tg to the student's teacher, once per student and level; coins to the student."""
    a.status, a.finished_at = "done", a.finished_at or now()
    a.score = a.auto_score + (a.manual_score or 0)
    s = await db.get(Student, a.student_id)
    d = now().date()
    threshold = await rate(db, "final_test_bonus_threshold", d)
    if a.score > threshold:
        g = await db.scalar(select(Group).join(GroupMember, GroupMember.group_id == Group.id)
                            .where(GroupMember.student_id == s.id, GroupMember.left_on.is_(None), Group.level_id == t.level_id))
        if g:
            await accrue_once(db, user_id=g.teacher_id, kind="final_test", amount=await rate(db, "teacher_final_test_bonus", d),
                              ref=(f"final:{t.level_id}", s.id), on=d, branch_id=g.branch_id,
                              description=f"Финальный тест: {s.full_name}, {a.score}/{t.max_score}", created_by=actor_id)
    if t.pass_score is None or a.score >= t.pass_score:
        await award_auto(db, s.id, "final_test", ("test", t.id), f"Финальный тест: {a.score}")


async def _bonus_teacher(db: DB, s: Student, t: Test) -> int | None:
    return await db.scalar(select(Group.teacher_id).join(GroupMember, GroupMember.group_id == Group.id)
                           .where(GroupMember.student_id == s.id, GroupMember.left_on.is_(None), Group.level_id == t.level_id))


async def _hold_for_approval(db: DB, a: Attempt, s: Student, t: Test) -> None:
    """A hand-entered score that would pay the person entering it waits for an admin (no self-approved bonuses)."""
    a.status = "needs_review"
    for uid in await crm_people(db, s.branch_id, "tests", "review"):
        if uid != a.reviewed_by:
            await notify_user(db, uid, "test", f"Подтвердите результат теста: {s.full_name}", body=f"{t.title}",
                              link=f"/tests/attempts/{a.id}")


@router.post("/tests/{test_id}/results", response_model=AttemptOut, status_code=201)
async def record_result(test_id: int, body: ResultIn, db: DB, actor: Actor = require("tests", "review")) -> AttemptOut:
    t = await db.get(Test, test_id)
    if t is None or t.kind != "final":
        raise not_found("Финальный тест")
    s = await get_student_scoped(db, actor, body.student_id)
    qs = list(await db.scalars(select(Question).where(Question.test_id == t.id, Question.archived_at.is_(None))))
    auto, needs = score(qs, body.answers or {})
    a = Attempt(test_id=t.id, student_id=s.id, user_id=s.user_id, branch_id=s.branch_id, answers=body.answers or {},
                auto_score=auto, manual_score=body.manual_score, started_at=now(), finished_at=now(),
                status="needs_review" if needs and body.manual_score is None else "done", reviewed_by=actor.id)
    if body.answers is None and body.manual_score is not None:
        a.auto_score = 0
    if a.auto_score + (a.manual_score or 0) > t.max_score:
        raise bad_request(f"Сумма больше максимума {t.max_score}")
    db.add(a)
    await db.flush()
    if a.status == "done" and body.manual_score is not None and await _bonus_teacher(db, s, t) == actor.id:
        await _hold_for_approval(db, a, s, t)
    elif a.status == "done":
        await finalize_final(db, a, t, actor.id)
    await write_audit(db, actor_id=actor.id, action="test.result", entity="attempt", entity_id=a.id, branch_id=s.branch_id,
                      ip=actor.ip, after={"student_id": s.id, "score": a.auto_score + (a.manual_score or 0)})
    await db.commit()
    return AttemptOut.model_validate(a)


class ReviewIn(BaseModel):
    manual_score: int = Field(ge=0)


@router.put("/attempts/{attempt_id}/review", response_model=AttemptOut)
async def review(attempt_id: int, body: ReviewIn, db: DB, actor: Actor = require("tests", "review")) -> AttemptOut:
    a = await db.get(Attempt, attempt_id)
    if a is None or a.student_id is None:
        raise not_found("Попытка")
    await get_student_scoped(db, actor, a.student_id)
    t = await db.get(Test, a.test_id)
    if a.auto_score + body.manual_score > t.max_score:
        raise bad_request(f"Сумма больше максимума {t.max_score}")
    if a.status == "done":
        raise forbidden("Результат уже утверждён")
    a.manual_score, a.reviewed_by = body.manual_score, actor.id
    s = await db.get(Student, a.student_id)
    if await _bonus_teacher(db, s, t) == actor.id and not actor.is_owner:
        await _hold_for_approval(db, a, s, t)
    else:
        await finalize_final(db, a, t, actor.id)
    await db.commit()
    return AttemptOut.model_validate(a)


@router.get("/students/{student_id}/tests", response_model=list[AttemptOut])
async def student_tests(student_id: int, db: DB, actor: CurrentActor) -> list[AttemptOut]:
    if not actor.can("tests", "view") and not actor.can("students", "view"):
        raise forbidden()
    s = await get_student_scoped(db, actor, student_id)
    return [AttemptOut.model_validate(a) for a in await db.scalars(select(Attempt).where(Attempt.student_id == s.id).order_by(Attempt.id.desc()))]


__all__ = ["router", "Lead"]
