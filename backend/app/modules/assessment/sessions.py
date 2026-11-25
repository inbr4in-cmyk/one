"""Group tests (owner, 25.11.2026): a test from the level's bank is planned for a group's lesson; at the lesson the
teacher starts it with a timer and the students take it online, each with the questions in his own order, one by
one and without going back. Leaving the page annuls the attempt until the teacher restores it. Score and time go
to the student's history; inside the test the students are ranked by score, then by time.

Everything that decides the result lives on the server: the order, the timer, the score. Correct answers are never
sent to a test taker."""
import random
from datetime import datetime, timedelta

from fastapi import APIRouter, Query
from pydantic import Field
from sqlalchemy import or_, select

from app.core.audit import write_audit
from app.core.deps import DB, Actor, CurrentActor, require
from app.core.errors import bad_request, conflict, forbidden, not_found
from app.core.permissions import NETWORK, OWN
from app.core.schemas import In
from app.models import Attempt, Group, GroupMember, Lesson, Question, Student, Test, TestSession, User
from app.models.learning import LessonStatus
from app.modules.assessment.router import Answer, finalize_final, score
from app.modules.portal.access import portal_student
from app.services import crm
from app.services.clock import now, today

router = APIRouter(tags=["tests"])
KINDS = ("progress", "final")


# ---------- shared ----------
async def _questions(db: DB, test_id: int) -> list[Question]:
    return list(await db.scalars(select(Question).where(Question.test_id == test_id, Question.archived_at.is_(None))
                                 .order_by(Question.order, Question.id)))


async def _close(db: DB, a: Attempt, t: Test, qs: list[Question], at: datetime) -> None:
    """The attempt ends: score what was answered, remember how long it took. An annulled attempt stays annulled."""
    a.finished_at = at
    a.duration_sec = max(0, int((at - a.started_at).total_seconds()))
    a.auto_score, needs = score(qs, a.answers or {})
    a.score = a.auto_score + (a.manual_score or 0)
    if a.status == "void":
        return
    if needs and a.manual_score is None:
        a.status = "needs_review"
    elif t.kind == "final" and a.student_id:
        await finalize_final(db, a, t, None)
    else:
        a.status = "done"


async def _expire(db: DB, ts: TestSession) -> None:
    """Time is up: whoever has not finished is finished with what he answered."""
    if ts.status != "running" or ts.ends_at is None or now() < ts.ends_at:
        return
    await _finish(db, ts, ts.ends_at)


async def _finish(db: DB, ts: TestSession, at: datetime) -> None:
    t = await db.get(Test, ts.test_id)
    qs = await _questions(db, t.id)
    for a in await db.scalars(select(Attempt).where(Attempt.session_id == ts.id, Attempt.finished_at.is_(None))):
        await _close(db, a, t, qs, at)
    ts.status, ts.finished_at = "finished", at
    await db.flush()


def _visible(actor: Actor):
    scope = actor.scope("tests", "view")
    if scope == NETWORK:
        return TestSession.id.is_not(None)
    if scope == OWN:
        mine = select(Group.id).where(Group.teacher_id == actor.id)
        subs = select(Lesson.id).where(or_(Lesson.teacher_id == actor.id, Lesson.actual_teacher_id == actor.id))
        return or_(TestSession.group_id.in_(mine), TestSession.lesson_id.in_(subs))
    return TestSession.branch_id.in_(actor.branch_ids or {-1})


async def _get(db: DB, actor: Actor, session_id: int, lock: bool = False) -> TestSession:
    q = select(TestSession).where(TestSession.id == session_id, _visible(actor))
    ts = await db.scalar(q.with_for_update() if lock else q)
    if ts is None:
        raise not_found("Тест группы")
    await _expire(db, ts)
    return ts


async def _brief(db: DB, rows: list[TestSession]) -> list[dict]:
    out = []
    for ts in rows:
        t = await db.get(Test, ts.test_id)
        g = await db.get(Group, ts.group_id)
        lesson = await db.get(Lesson, ts.lesson_id) if ts.lesson_id else None
        out.append({"id": ts.id, "test_id": t.id, "title": t.title, "kind": t.kind, "group_id": g.id, "group_name": g.name,
                    "lesson_id": ts.lesson_id, "lesson_at": lesson.starts_at if lesson else None, "status": ts.status,
                    "time_limit_min": ts.time_limit_min, "started_at": ts.started_at, "ends_at": ts.ends_at,
                    "finished_at": ts.finished_at})
    return out


def rank(rows: list[dict]) -> None:
    """Place inside the test: more points first, equal points by the shorter time. Annulled attempts have no place."""
    done = sorted((r for r in rows if r["status"] in ("done", "needs_review")), key=lambda r: (-r["score"], r["duration_sec"] or 0))
    for i, r in enumerate(done, 1):
        r["place"] = i


# ---------- staff: plan, run, watch ----------
class PlanIn(In):
    group_id: int = Field(ge=1)
    test_id: int = Field(ge=1)
    lesson_id: int = Field(ge=1)


@router.get("/test-sessions")
async def list_sessions(db: DB, actor: Actor = require("tests", "view"), group_id: int | None = Query(None, ge=1),
                        active: bool = False) -> list[dict]:
    q = select(TestSession).where(_visible(actor))
    if group_id:
        q = q.where(TestSession.group_id == group_id)
    if active:
        q = q.where(TestSession.status != "finished")
    rows = list(await db.scalars(q.order_by(TestSession.id.desc()).limit(200)))
    for ts in rows:
        await _expire(db, ts)
    await db.commit()
    return await _brief(db, rows)


@router.post("/test-sessions", status_code=201)
async def plan(body: PlanIn, db: DB, actor: Actor = require("tests", "review")) -> dict:
    """«Запланировать тест»: the group, a progress or final test of the group's level, the lesson it is held at."""
    from app.modules.academics.router import _get_group

    g = await _get_group(db, actor, body.group_id)
    if g.archived_at is not None:
        raise bad_request("Группа завершена")
    t = await db.get(Test, body.test_id)
    if t is None or t.archived_at is not None or t.kind not in KINDS:
        raise not_found("Тест")
    if t.level_id != g.level_id:
        raise bad_request("Тест другого уровня")
    if not await _questions(db, t.id):
        raise bad_request("В тесте ещё нет вопросов")
    lesson = await db.get(Lesson, body.lesson_id)
    if lesson is None or lesson.group_id != g.id or lesson.status == LessonStatus.CANCELLED:
        raise bad_request("Выберите урок этой группы")
    if await db.scalar(select(TestSession.id).where(TestSession.lesson_id == lesson.id, TestSession.status != "finished")):
        raise conflict("На этот урок тест уже запланирован")
    ts = TestSession(test_id=t.id, group_id=g.id, lesson_id=lesson.id, branch_id=g.branch_id,
                     time_limit_min=t.time_limit_min or 60, created_by=actor.id)
    db.add(ts)
    await db.flush()
    teacher_id = lesson.actual_teacher_id or lesson.teacher_id
    if teacher_id != actor.id:
        from app.services.clock import local
        await crm.alert(db, teacher_id, "test", f"{g.name}: {t.title} {local(lesson.starts_at):%d.%m в %H:%M}",
                        body="Тест запланирован на ваш урок. Запустите его на уроке.", link=f"/tests/sessions/{ts.id}")
    await write_audit(db, actor_id=actor.id, action="test.plan", entity="test_session", entity_id=ts.id, branch_id=g.branch_id,
                      ip=actor.ip, after={"group_id": g.id, "test_id": t.id, "lesson_id": lesson.id})
    await db.commit()
    return (await _brief(db, [ts]))[0]


@router.delete("/test-sessions/{session_id}", status_code=204)
async def unplan(session_id: int, db: DB, actor: Actor = require("tests", "review")) -> None:
    ts = await _get(db, actor, session_id)
    if ts.status != "planned":
        raise conflict("Тест уже запущен, убрать его нельзя")
    await write_audit(db, actor_id=actor.id, action="test.unplan", entity="test_session", entity_id=ts.id, branch_id=ts.branch_id, ip=actor.ip)
    await db.delete(ts)
    await db.commit()


@router.get("/test-sessions/{session_id}")
async def session(session_id: int, db: DB, actor: Actor = require("tests", "view")) -> dict:
    ts = await _get(db, actor, session_id)
    await db.commit()
    lesson = await db.get(Lesson, ts.lesson_id) if ts.lesson_id else None
    day = (lesson.starts_at if lesson else ts.created_at).date()
    total = len(await _questions(db, ts.test_id))
    students = list(await db.scalars(
        select(Student).join(GroupMember, GroupMember.student_id == Student.id)
        .where(GroupMember.group_id == ts.group_id, GroupMember.joined_on <= day,
               or_(GroupMember.left_on.is_(None), GroupMember.left_on > day)).order_by(Student.full_name)))
    attempts = {a.student_id: a for a in await db.scalars(select(Attempt).where(Attempt.session_id == ts.id))}
    extra = [sid for sid in attempts if sid not in {s.id for s in students}]
    if extra:
        students += list(await db.scalars(select(Student).where(Student.id.in_(extra))))
    rows = []
    for s in students:
        a = attempts.get(s.id)
        rows.append({"student_id": s.id, "full_name": s.full_name, "has_login": s.user_id is not None,
                     "status": a.status if a else "none", "answered": len(a.answers or {}) if a else 0,
                     "score": a.score if a and a.finished_at else None, "duration_sec": a.duration_sec if a else None,
                     "voided_at": a.voided_at if a else None, "restores": a.restores if a else 0, "place": None})
    rank(rows)
    t = await db.get(Test, ts.test_id)
    return {**(await _brief(db, [ts]))[0], "max_score": sum(q.points for q in await _questions(db, t.id)), "questions": total,
            "now": now(), "can_run": actor.can("tests", "review"), "rows": rows}


class StartIn(In):
    time_limit_min: int = Field(default=60, ge=5, le=300)


@router.post("/test-sessions/{session_id}/start")
async def start(session_id: int, body: StartIn, db: DB, actor: Actor = require("tests", "review")) -> dict:
    """The teacher starts the test at the lesson; the timer (60 min unless changed) runs for everyone from now."""
    ts = await _get(db, actor, session_id, lock=True)
    if ts.status != "planned":
        raise conflict("Тест уже запущен")
    ts.status, ts.started_at, ts.time_limit_min = "running", now(), body.time_limit_min
    ts.ends_at = ts.started_at + timedelta(minutes=body.time_limit_min)
    t = await db.get(Test, ts.test_id)
    day = today()
    for uid in await db.scalars(select(Student.user_id).join(GroupMember, GroupMember.student_id == Student.id).where(
            GroupMember.group_id == ts.group_id, GroupMember.joined_on <= day,
            or_(GroupMember.left_on.is_(None), GroupMember.left_on > day), Student.user_id.is_not(None))):
        await crm.alert(db, uid, "test", f"Начался тест: {t.title}", body="Откройте тест и начните.", link=f"/portal/test/{ts.id}")
    await write_audit(db, actor_id=actor.id, action="test.start", entity="test_session", entity_id=ts.id, branch_id=ts.branch_id,
                      ip=actor.ip, after={"minutes": body.time_limit_min})
    await db.commit()
    return await session(session_id, db, actor)


@router.post("/test-sessions/{session_id}/finish")
async def finish(session_id: int, db: DB, actor: Actor = require("tests", "review")) -> dict:
    ts = await _get(db, actor, session_id, lock=True)
    if ts.status == "running":
        await _finish(db, ts, now())
        await write_audit(db, actor_id=actor.id, action="test.finish", entity="test_session", entity_id=ts.id, branch_id=ts.branch_id, ip=actor.ip)
    await db.commit()
    return await session(session_id, db, actor)


class RestoreIn(In):
    student_id: int = Field(ge=1)


@router.post("/test-sessions/{session_id}/restore")
async def restore(session_id: int, body: RestoreIn, db: DB, actor: Actor = require("tests", "review")) -> dict:
    """«Восстановить»: an annulled attempt goes on from the question it stopped at. The timer was not paused."""
    ts = await _get(db, actor, session_id, lock=True)
    if ts.status != "running":
        raise conflict("Тест не идёт")
    a = await db.scalar(select(Attempt).where(Attempt.session_id == ts.id, Attempt.student_id == body.student_id).with_for_update())
    if a is None or a.status != "void":
        raise bad_request("Эта попытка не аннулирована")
    a.status, a.voided_at, a.restores = "in_progress", None, a.restores + 1
    await write_audit(db, actor_id=actor.id, action="test.restore", entity="attempt", entity_id=a.id, branch_id=ts.branch_id,
                      ip=actor.ip, after={"student_id": a.student_id, "restores": a.restores})
    await db.commit()
    return await session(session_id, db, actor)


# ---------- the student takes it ----------
async def _mine(db: DB, actor: Actor, session_id: int, student_id: int, lock: bool = False) -> tuple[TestSession, Student]:
    s = await portal_student(db, actor, student_id, allow_blocked=True)
    q = select(TestSession).where(TestSession.id == session_id)
    ts = await db.scalar(q.with_for_update() if lock else q)
    if ts is None:
        raise not_found("Тест")
    member = await db.scalar(select(GroupMember.id).where(GroupMember.group_id == ts.group_id, GroupMember.student_id == s.id,
                                                          GroupMember.left_on.is_(None)))
    mine = await db.scalar(select(Attempt.id).where(Attempt.session_id == ts.id, Attempt.student_id == s.id))
    if member is None and mine is None:
        raise not_found("Тест")
    await _expire(db, ts)
    return ts, s


async def _state(db: DB, ts: TestSession, s: Student) -> dict:
    t = await db.get(Test, ts.test_id)
    a = await db.scalar(select(Attempt).where(Attempt.session_id == ts.id, Attempt.student_id == s.id))
    out = {"id": ts.id, "title": t.title, "status": ts.status, "ends_at": ts.ends_at, "now": now(), "time_limit_min": ts.time_limit_min,
           "attempt": None, "question": None}
    if a is None:
        return out
    order = a.q_order or []
    out["attempt"] = {"status": a.status, "position": a.position, "total": len(order),
                      "score": a.score if a.finished_at and a.status != "needs_review" else None,
                      "max_score": None, "duration_sec": a.duration_sec}
    if a.finished_at:
        out["attempt"]["max_score"] = sum(q.points for q in await _questions(db, t.id))
    if a.status == "in_progress" and ts.status == "running" and a.position < len(order):
        q = await db.get(Question, order[a.position])
        out["question"] = {"id": q.id, "kind": q.kind, "text": q.text, "options": q.options or []}
    return out


@router.get("/portal/tests")
async def my_tests(db: DB, actor: CurrentActor, student_id: int = Query(ge=1)) -> list[dict]:
    """Tests of the student's groups that are running now or planned for today."""
    s = await portal_student(db, actor, student_id, allow_blocked=True)
    gids = select(GroupMember.group_id).where(GroupMember.student_id == s.id, GroupMember.left_on.is_(None))
    rows = list(await db.scalars(select(TestSession).where(TestSession.group_id.in_(gids), TestSession.status != "finished")
                                 .order_by(TestSession.id)))
    out = []
    for ts in rows:
        await _expire(db, ts)
        if ts.status == "finished":
            continue
        t = await db.get(Test, ts.test_id)
        a = await db.scalar(select(Attempt.status).where(Attempt.session_id == ts.id, Attempt.student_id == s.id))
        out.append({"id": ts.id, "title": t.title, "status": ts.status, "ends_at": ts.ends_at, "my_status": a})
    await db.commit()
    return out


class WhoIn(In):
    student_id: int = Field(ge=1)


@router.get("/portal/tests/{session_id}")
async def my_state(session_id: int, db: DB, actor: CurrentActor, student_id: int = Query(ge=1)) -> dict:
    ts, s = await _mine(db, actor, session_id, student_id)
    await db.commit()
    return await _state(db, ts, s)


@router.post("/portal/tests/{session_id}/begin")
async def begin(session_id: int, body: WhoIn, db: DB, actor: CurrentActor) -> dict:
    """The student opens the test: his own order of the questions is fixed now and never changes."""
    ts, s = await _mine(db, actor, session_id, body.student_id, lock=True)
    if ts.status != "running":
        raise conflict("Тест ещё не начался" if ts.status == "planned" else "Тест закончен")
    a = await db.scalar(select(Attempt).where(Attempt.session_id == ts.id, Attempt.student_id == s.id))
    if a is None:
        ids = [q.id for q in await _questions(db, ts.test_id)]
        random.SystemRandom().shuffle(ids)
        a = Attempt(test_id=ts.test_id, session_id=ts.id, student_id=s.id, user_id=s.user_id, branch_id=s.branch_id, answers={},
                    q_order=ids, position=0, started_at=now(), status="in_progress", taker_name=s.full_name)
        db.add(a)
    await db.commit()
    return await _state(db, ts, s)


class AnswerIn(In):
    student_id: int = Field(ge=1)
    question_id: int = Field(ge=1)
    answer: Answer


@router.post("/portal/tests/{session_id}/answer")
async def answer(session_id: int, body: AnswerIn, db: DB, actor: CurrentActor) -> dict:
    """One question at a time, in the student's order; an answered question cannot be opened again."""
    ts, s = await _mine(db, actor, session_id, body.student_id, lock=True)
    a = await db.scalar(select(Attempt).where(Attempt.session_id == ts.id, Attempt.student_id == s.id).with_for_update())
    if a is None or ts.status != "running" or a.status != "in_progress":
        await db.commit()
        return await _state(db, ts, s)
    order = a.q_order or []
    if a.position >= len(order) or order[a.position] != body.question_id:
        raise conflict("Этот вопрос уже пройден")
    q = await db.get(Question, body.question_id)
    v = body.answer
    if q.kind == "text":
        if not isinstance(v, str) or not v.strip():
            raise bad_request("Напишите ответ")
        v = v.strip()
    else:
        picked = sorted(set(v)) if isinstance(v, list) else [v] if isinstance(v, int) else []
        if not picked or any(i >= len(q.options or []) for i in picked) or (q.kind == "single" and len(picked) != 1):
            raise bad_request("Выберите ответ")
        v = picked
    a.answers = {**(a.answers or {}), str(q.id): v}
    a.position += 1
    if a.position >= len(order):
        await _close(db, a, await db.get(Test, ts.test_id), await _questions(db, ts.test_id), now())
    await db.commit()
    return await _state(db, ts, s)


@router.post("/portal/tests/{session_id}/leave")
async def leave(session_id: int, body: WhoIn, db: DB, actor: CurrentActor) -> dict:
    """The student left the test page (another tab, minimised): the attempt is annulled until the teacher restores it."""
    ts, s = await _mine(db, actor, session_id, body.student_id, lock=True)
    a = await db.scalar(select(Attempt).where(Attempt.session_id == ts.id, Attempt.student_id == s.id).with_for_update())
    if a is not None and ts.status == "running" and a.status == "in_progress":
        a.status, a.voided_at = "void", now()
        lesson = await db.get(Lesson, ts.lesson_id) if ts.lesson_id else None
        g = await db.get(Group, ts.group_id)
        teacher_id = (lesson.actual_teacher_id or lesson.teacher_id) if lesson else g.teacher_id
        if teacher_id and await db.get(User, teacher_id):
            await crm.alert(db, teacher_id, "test", f"{s.full_name} вышел из теста", body="Попытка аннулирована. Можно восстановить.",
                            link=f"/tests/sessions/{ts.id}")
    await db.commit()
    return await _state(db, ts, s)
