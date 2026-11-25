"""Group tests (owner, 25.11.2026): a test from the level's bank is planned for a group's lesson; at the lesson the
teacher starts it with a timer and the students take it online, each with the questions in his own order, one by
one and without going back. Leaving the page annuls the attempt until the teacher restores it. Score and time go
to the student's history; inside the test the students are ranked by score, then by time.

Everything that decides the result lives on the server: the order, the timer, the score. Correct answers are never
sent to a test taker."""
from datetime import datetime, timedelta

from fastapi import APIRouter, File, Form, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import Field
from sqlalchemy import or_, select

from app.core.audit import write_audit
from app.core.deps import DB, Actor, CurrentActor, require
from app.core.errors import bad_request, conflict, forbidden, not_found
from app.core.permissions import NETWORK, OWN
from app.core.schemas import In
from app.models import Attempt, Group, GroupMember, Lesson, Question, Student, Test, TestSession, User
from app.models.learning import LessonStatus
from app.modules.assessment import engine
from app.modules.assessment.router import Answer, finalize_final
from app.modules.portal.access import portal_student
from app.modules.students.scope import get_student_scoped
from app.services import crm
from app.services.clock import now, today

router = APIRouter(tags=["tests"])
KINDS = ("progress", "final")


# ---------- shared ----------
_questions = engine.questions
_close = engine.close


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
        rows.append({"student_id": s.id, "full_name": s.full_name, "has_login": s.user_id is not None, "attempt_id": a.id if a else None,
                     "status": a.status if a else "none", "answered": len(a.answers or {}) if a else 0,
                     "score": a.score if a and a.finished_at else None, "duration_sec": a.duration_sec if a else None,
                     "voided_at": a.voided_at if a else None, "restores": a.restores if a else 0, "place": None})
    rank(rows)
    t = await db.get(Test, ts.test_id)
    return {**(await _brief(db, [ts]))[0], "max_score": sum(q.points for q in await _questions(db, t.id)), "questions": total,
            "now": now(), "can_run": actor.can("tests", "review"), "rows": rows,
            "suggested_min": engine.total_minutes(t) + 5 if t.parts else None}


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
    """«Восстановить»: an annulled attempt goes on from where it stopped. The test's own end was not moved."""
    ts = await _get(db, actor, session_id, lock=True)
    if ts.status != "running":
        raise conflict("Тест не идёт")
    a = await db.scalar(select(Attempt).where(Attempt.session_id == ts.id, Attempt.student_id == body.student_id).with_for_update())
    if a is None or a.status != "void":
        raise bad_request("Эта попытка не аннулирована")
    engine.restore(a, now())
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
    qs = await _questions(db, t.id)
    if t.parts:
        out["outline"] = engine.outline(t, qs)
    if a is None:
        return out
    order = a.q_order or []
    out["attempt"] = {"id": a.id, "status": a.status, "position": a.position, "total": len(t.parts) if t.parts else len(order),
                      "score": a.score if a.finished_at and a.status != "needs_review" else None,
                      "max_score": None, "duration_sec": a.duration_sec}
    if a.finished_at:
        out["attempt"]["max_score"] = sum(q.points for q in await _questions(db, t.id))
    if t.parts:
        out["stage"] = engine.stage_state(a, t, qs) if ts.status == "running" else None
    elif a.status == "in_progress" and ts.status == "running" and a.position < len(order):
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


async def _lapse(db: DB, ts: TestSession, s: Student) -> Attempt | None:
    a = await db.scalar(select(Attempt).where(Attempt.session_id == ts.id, Attempt.student_id == s.id).with_for_update())
    if a is not None and ts.status == "running":
        t = await db.get(Test, ts.test_id)
        if t.parts:
            await engine.lapse(db, a, t, await _questions(db, t.id), now())
    return a


class WhoIn(In):
    student_id: int = Field(ge=1)


@router.get("/portal/tests/{session_id}")
async def my_state(session_id: int, db: DB, actor: CurrentActor, student_id: int = Query(ge=1)) -> dict:
    ts, s = await _mine(db, actor, session_id, student_id)
    await _lapse(db, ts, s)
    await db.commit()
    return await _state(db, ts, s)


@router.post("/portal/tests/{session_id}/begin")
async def begin(session_id: int, body: WhoIn, db: DB, actor: CurrentActor) -> dict:
    """The student opens the test; the clock of the first stage starts for him now."""
    ts, s = await _mine(db, actor, session_id, body.student_id, lock=True)
    if ts.status != "running":
        raise conflict("Тест ещё не начался" if ts.status == "planned" else "Тест закончен")
    a = await db.scalar(select(Attempt).where(Attempt.session_id == ts.id, Attempt.student_id == s.id))
    if a is None:
        # the same order for everyone (owner, 25.11.2026: no shuffling)
        ids = [q.id for q in await _questions(db, ts.test_id)]
        a = Attempt(test_id=ts.test_id, session_id=ts.id, student_id=s.id, user_id=s.user_id, branch_id=s.branch_id, answers={},
                    q_order=ids, position=0, started_at=now(), part_started_at=now(), status="in_progress", taker_name=s.full_name)
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
    if a is None or ts.status != "running" or a.status != "in_progress" or (await db.get(Test, ts.test_id)).parts:
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


class SaveIn(In):
    student_id: int = Field(ge=1)
    part_id: str = Field(min_length=1, max_length=16)
    answers: dict[str, list[int] | str | None] = Field(default={}, max_length=100)
    final: bool = False


@router.post("/portal/tests/{session_id}/save")
async def save_stage(session_id: int, body: SaveIn, db: DB, actor: CurrentActor) -> dict:
    """A staged test: the answers of the current stage. `final` closes the stage for good and opens the next."""
    ts, s = await _mine(db, actor, session_id, body.student_id, lock=True)
    a = await db.scalar(select(Attempt).where(Attempt.session_id == ts.id, Attempt.student_id == s.id).with_for_update())
    t = await db.get(Test, ts.test_id)
    if a is not None and ts.status == "running" and t.parts:
        await engine.save(db, a, t, await _questions(db, t.id), body.part_id, body.answers, body.final, now())
    await db.commit()
    return await _state(db, ts, s)


async def _read_video(file: UploadFile) -> bytes:
    data = await file.read(engine.VIDEO_MAX + 1)
    if len(data) > engine.VIDEO_MAX:
        raise bad_request("Видео слишком большое")
    return data


@router.post("/portal/tests/{session_id}/video")
async def save_video(session_id: int, db: DB, actor: CurrentActor, student_id: int = Form(ge=1), question_id: int = Form(ge=1),
                     file: UploadFile = File(...)) -> dict:
    ts, s = await _mine(db, actor, session_id, student_id, lock=True)
    a = await db.scalar(select(Attempt).where(Attempt.session_id == ts.id, Attempt.student_id == s.id).with_for_update())
    t = await db.get(Test, ts.test_id)
    if a is None or ts.status != "running" or not t.parts:
        raise conflict("Тест не идёт")
    await engine.save_video(db, a, t, await _questions(db, t.id), question_id, file.content_type or "", await _read_video(file), now())
    await db.commit()
    return await _state(db, ts, s)


# ---------- «Тестовый режим»: staff take a staged test themselves ----------
def _trial_state(a: Attempt, t: Test, qs: list) -> dict:
    ps = engine.stages(t)
    out = {"id": a.id, "title": t.title, "status": "finished" if a.finished_at else "running", "ends_at": None, "now": now(),
           "time_limit_min": engine.total_minutes(t), "question": None, "outline": engine.outline(t, qs), "trial": True,
           "attempt": {"id": a.id, "status": a.status, "position": a.position, "total": len(ps),
                       "score": a.score if a.finished_at and a.status != "needs_review" else None,
                       "max_score": sum(q.points for q in qs) if a.finished_at else None, "duration_sec": a.duration_sec},
           "stage": engine.stage_state(a, t, qs)}
    return out


async def _trial(db: DB, actor: Actor, attempt_id: int) -> tuple[Attempt, Test, list]:
    a = await db.scalar(select(Attempt).where(Attempt.id == attempt_id, Attempt.trial.is_(True), Attempt.user_id == actor.id).with_for_update())
    if a is None:
        raise not_found("Попытка")
    t = await db.get(Test, a.test_id)
    return a, t, await _questions(db, t.id)


@router.post("/tests/{test_id}/trial", status_code=201)
async def trial_begin(test_id: int, db: DB, actor: Actor = require("tests", "review")) -> dict:
    """A staff member takes the test as a student would. Nothing of it reaches students, ratings or pay."""
    t = await db.get(Test, test_id)
    if t is None or t.archived_at is not None or not t.parts:
        raise not_found("Тест")
    qs = await _questions(db, t.id)
    for old in await db.scalars(select(Attempt).where(Attempt.test_id == t.id, Attempt.trial.is_(True), Attempt.user_id == actor.id,
                                                      Attempt.finished_at.is_(None))):
        old.status = "in_progress" if old.status == "void" else old.status
        await engine.close(db, old, t, qs, now())
    me = await db.get(User, actor.id)
    a = Attempt(test_id=t.id, user_id=actor.id, trial=True, answers={}, position=0, started_at=now(), part_started_at=now(),
                status="in_progress", taker_name=me.full_name)
    db.add(a)
    await db.commit()
    return _trial_state(a, t, qs)


@router.get("/test-trials/{attempt_id}")
async def trial_state(attempt_id: int, db: DB, actor: Actor = require("tests", "review")) -> dict:
    a, t, qs = await _trial(db, actor, attempt_id)
    await engine.lapse(db, a, t, qs, now())
    await db.commit()
    return _trial_state(a, t, qs)


class TrialSaveIn(In):
    part_id: str = Field(min_length=1, max_length=16)
    answers: dict[str, list[int] | str | None] = Field(default={}, max_length=100)
    final: bool = False


@router.post("/test-trials/{attempt_id}/save")
async def trial_save(attempt_id: int, body: TrialSaveIn, db: DB, actor: Actor = require("tests", "review")) -> dict:
    a, t, qs = await _trial(db, actor, attempt_id)
    await engine.save(db, a, t, qs, body.part_id, body.answers, body.final, now())
    await db.commit()
    return _trial_state(a, t, qs)


@router.post("/test-trials/{attempt_id}/video")
async def trial_video(attempt_id: int, db: DB, actor: Actor = require("tests", "review"), question_id: int = Form(ge=1),
                      file: UploadFile = File(...)) -> dict:
    a, t, qs = await _trial(db, actor, attempt_id)
    await engine.save_video(db, a, t, qs, question_id, file.content_type or "", await _read_video(file), now())
    await db.commit()
    return _trial_state(a, t, qs)


@router.post("/test-trials/{attempt_id}/leave")
async def trial_leave(attempt_id: int, db: DB, actor: Actor = require("tests", "review")) -> dict:
    a, t, qs = await _trial(db, actor, attempt_id)
    await engine.lapse(db, a, t, qs, now())
    if a.status == "in_progress" and not a.finished_at:
        a.status, a.voided_at = "void", now()
    await db.commit()
    return _trial_state(a, t, qs)


@router.post("/test-trials/{attempt_id}/restore")
async def trial_restore(attempt_id: int, db: DB, actor: Actor = require("tests", "review")) -> dict:
    """In the trial the person restores himself: with students it is the teacher's button."""
    a, t, qs = await _trial(db, actor, attempt_id)
    if a.status == "void" and not a.finished_at:
        engine.restore(a, now())
    await db.commit()
    return _trial_state(a, t, qs)


@router.get("/tests/{test_id}/trials")
async def trials(test_id: int, db: DB, actor: Actor = require("tests", "review")) -> list[dict]:
    rows = await db.scalars(select(Attempt).where(Attempt.test_id == test_id, Attempt.trial.is_(True), Attempt.finished_at.is_not(None))
                            .order_by(Attempt.id.desc()).limit(30))
    return [{"id": a.id, "taker": a.taker_name, "status": a.status, "score": a.score, "duration_sec": a.duration_sec,
             "finished_at": a.finished_at} for a in rows]


# ---------- checking: every answer, writing and speaking marked by hand ----------
async def _checked(db: DB, actor: Actor, attempt_id: int, lock: bool = False) -> tuple[Attempt, Test, list]:
    q = select(Attempt).where(Attempt.id == attempt_id)
    a = await db.scalar(q.with_for_update() if lock else q)
    if a is None or not (a.trial or a.student_id):
        raise not_found("Попытка")
    if a.student_id:
        await get_student_scoped(db, actor, a.student_id)
    t = await db.get(Test, a.test_id)
    return a, t, await _questions(db, t.id)


@router.get("/attempts/{attempt_id}/detail")
async def attempt_detail(attempt_id: int, db: DB, actor: Actor = require("tests", "review")) -> dict:
    a, t, qs = await _checked(db, actor, attempt_id)
    return engine.detail(a, t, qs)


class MarksIn(In):
    marks: dict[str, int] = Field(max_length=100)


@router.put("/attempts/{attempt_id}/marks")
async def set_marks(attempt_id: int, body: MarksIn, db: DB, actor: Actor = require("tests", "review")) -> dict:
    """Points for the answers a person checks (writing, speaking). When all of them are marked the result is final."""
    a, t, qs = await _checked(db, actor, attempt_id, lock=True)
    if a.finished_at is None:
        raise conflict("Тест ещё не закончен")
    manual = {str(q.id): q for q in qs if q.kind in ("text", "video")}
    marks = dict(a.marks or {})
    for k, v in body.marks.items():
        if k not in manual or not 0 <= v <= manual[k].points:
            raise bad_request("Баллы больше, чем даёт вопрос")
        marks[k] = v
    a.marks, a.manual_score, a.reviewed_by = marks, sum(marks.values()), actor.id
    a.score = a.auto_score + a.manual_score
    answered = [k for k in manual if (a.answers or {}).get(k)]
    if a.status == "needs_review" and all(k in marks for k in answered):
        if t.kind == "final" and a.student_id:
            await finalize_final(db, a, t, actor.id)
        else:
            a.status = "done"
    await write_audit(db, actor_id=actor.id, action="test.marks", entity="attempt", entity_id=a.id, branch_id=a.branch_id, ip=actor.ip,
                      after={"manual_score": a.manual_score})
    await db.commit()
    return engine.detail(a, t, qs)


@router.get("/attempts/{attempt_id}/video/{question_id}")
async def attempt_video(attempt_id: int, question_id: int, db: DB, actor: Actor = require("tests", "review")) -> FileResponse:
    import os

    a, _, _ = await _checked(db, actor, attempt_id)
    v = (a.answers or {}).get(str(question_id))
    if not isinstance(v, dict) or v.get("video") not in engine.VIDEO_TYPES.values():
        raise not_found("Видео")
    path = engine.video_path(a.id, question_id, v["video"])
    if not os.path.isfile(path):
        raise not_found("Видео")
    return FileResponse(path, media_type="video/webm" if v["video"] == ".webm" else "video/mp4", headers={"Cache-Control": "private, no-store"})


@router.get("/tests/{test_id}/outline")
async def test_outline(test_id: int, db: DB, actor: Actor = require("tests", "review")) -> dict:
    """What a staff member sees before starting a trial run: the stages and their time."""
    t = await db.get(Test, test_id)
    if t is None or t.archived_at is not None or not t.parts:
        raise not_found("Тест")
    return {"title": t.title, **engine.outline(t, await _questions(db, t.id))}
