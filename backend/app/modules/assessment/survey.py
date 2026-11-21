"""«Оценка урока» by QR (owner, 21.11.2026). Staff pick a group, the screen shows a QR code and a link for that
group's lesson; the students answer a few questions without logging in. The answers rate the lesson and the teacher
and are seen only by the owner and branch admins (students.archive)."""

import secrets
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Request
from pydantic import Field
from sqlalchemy import func, select

from app.core.audit import write_audit
from app.core.deps import DB, Actor, require, require_staff
from app.core.errors import bad_request, conflict, not_found
from app.core.ratelimit import client_ip, hit
from app.core.schemas import In
from app.models import Group, Lesson, LessonSurvey, LessonSurveyAnswer, Setting, User
from app.models.learning import LessonStatus
from app.modules.academics.router import group_filter
from app.services.clock import local, local_range, now, today

router = APIRouter(tags=["lesson-survey"])
KEY = "lesson_survey_questions"
DEFAULT_QUESTIONS = [
    {"text": "Понравился ли вам урок?", "kind": "stars"},
    {"text": "Насколько понятно объяснял учитель?", "kind": "stars"},
    {"text": "Что можно улучшить?", "kind": "text"},
]
OPEN_HOURS = 24  # the link takes answers until a day after the lesson


class QuestionIn(In):
    text: str = Field(min_length=3, max_length=200)
    kind: str = Field(pattern="^(stars|text)$")


class QuestionsIn(In):
    questions: list[QuestionIn] = Field(min_length=1, max_length=6)


async def _questions(db: DB) -> list[dict]:
    s = await db.scalar(select(Setting).where(Setting.key == KEY))
    return (s.value or {}).get("v") or DEFAULT_QUESTIONS if s else DEFAULT_QUESTIONS


@router.get("/lesson-surveys/questions")
async def get_questions(db: DB, actor: Actor = require_staff()) -> list[dict]:
    return await _questions(db)


@router.put("/lesson-surveys/questions")
async def set_questions(body: QuestionsIn, db: DB, actor: Actor = require("students", "archive")) -> list[dict]:
    """New questions go to the links made from now on; a link already shown keeps the questions it was made with."""
    qs = [q.model_dump() for q in body.questions]
    if not any(q["kind"] == "stars" for q in qs):
        raise bad_request("Нужен хотя бы один вопрос с оценкой от 1 до 5")
    s = await db.scalar(select(Setting).where(Setting.key == KEY))
    before = (s.value or {}).get("v") if s else None
    if s is None:
        db.add(Setting(key=KEY, value={"v": qs}, updated_by=actor.id))
    else:
        s.value, s.updated_by = {"v": qs}, actor.id
    await write_audit(db, actor_id=actor.id, action="lesson_survey.questions", entity="setting", entity_id=0, ip=actor.ip,
                      before={"questions": before}, after={"questions": qs})
    await db.commit()
    return qs


class SurveyIn(In):
    group_id: int = Field(ge=1)


def _lesson_title(lesson: Lesson) -> str:
    return local(lesson.starts_at).strftime("%d.%m %H:%M")


@router.post("/lesson-surveys")
async def open_survey(body: SurveyIn, db: DB, actor: Actor = require_staff()) -> dict:
    """The QR for the group's lesson of today (the one going on or the last one that started); if there was none
    today — for the last lesson of the past week. One link per lesson, however many times it is asked for."""
    g = await db.scalar(select(Group).where(Group.id == body.group_id, group_filter(actor)))
    if g is None:
        raise not_found("Группа")
    t = now()
    base = select(Lesson).where(Lesson.group_id == g.id, Lesson.status != LessonStatus.CANCELLED)
    lesson = await db.scalar(base.where(Lesson.starts_at <= t + timedelta(minutes=30), Lesson.starts_at > t - timedelta(days=7))
                             .order_by(Lesson.starts_at.desc()).limit(1))
    if lesson is None:
        raise conflict("У этой группы не было уроков за последнюю неделю")
    sv = await db.scalar(select(LessonSurvey).where(LessonSurvey.lesson_id == lesson.id))
    if sv is None:
        sv = LessonSurvey(lesson_id=lesson.id, token=secrets.token_urlsafe(18), created_by=actor.id,
                          closes_at=max(lesson.ends_at, t) + timedelta(hours=OPEN_HOURS), questions=await _questions(db))
        db.add(sv)
        await db.flush()
        await write_audit(db, actor_id=actor.id, action="lesson_survey.open", entity="lesson", entity_id=lesson.id,
                          branch_id=lesson.branch_id, ip=actor.ip, after={"group": g.name})
    elif sv.closes_at < t + timedelta(hours=1):
        sv.closes_at = t + timedelta(hours=OPEN_HOURS)  # shown again later: the link works for another day
    await db.commit()
    answers = await db.scalar(select(func.count()).select_from(LessonSurveyAnswer).where(LessonSurveyAnswer.survey_id == sv.id))
    return {"token": sv.token, "path": f"/r/{sv.token}", "lesson_id": lesson.id, "lesson": _lesson_title(lesson),
            "group": g.name, "answers": answers, "closes_at": sv.closes_at}


# ---------- the students' page (public, no login) ----------
async def _by_token(db: DB, token: str) -> LessonSurvey:
    sv = await db.scalar(select(LessonSurvey).where(LessonSurvey.token == token)) if 10 <= len(token) <= 40 else None
    if sv is None:
        raise not_found("Ссылка")
    return sv


@router.get("/public/lesson-survey/{token}")
async def public_survey(token: str, db: DB) -> dict:
    sv = await _by_token(db, token)
    lesson = await db.get(Lesson, sv.lesson_id)
    g = await db.get(Group, lesson.group_id) if lesson.group_id else None
    teacher = await db.get(User, lesson.actual_teacher_id or lesson.teacher_id)
    return {"group": g.name if g else None, "teacher": teacher.full_name if teacher else None, "lesson": _lesson_title(lesson),
            "open": sv.closes_at > now(), "questions": sv.questions}


class AnswersIn(In):
    answers: list[int | str | None] = Field(min_length=1, max_length=6)


@router.post("/public/lesson-survey/{token}", status_code=201)
async def answer(token: str, body: AnswersIn, request: Request, db: DB) -> dict:
    await hit(f"lsurvey:{client_ip(request)}", 40, 3600)  # a whole class may share the school Wi-Fi
    sv = await _by_token(db, token)
    if sv.closes_at <= now():
        raise conflict("Опрос по этому уроку уже закрыт")
    if len(body.answers) != len(sv.questions):
        raise bad_request("Ответьте на все вопросы")
    clean: list[int | str | None] = []
    for q, a in zip(sv.questions, body.answers):
        if q["kind"] == "stars":
            if not isinstance(a, int) or not 1 <= a <= 5:
                raise bad_request("Поставьте оценку от 1 до 5")
            clean.append(a)
        else:
            clean.append((str(a).strip()[:1000] or None) if a is not None else None)
    db.add(LessonSurveyAnswer(survey_id=sv.id, at=now(), answers=clean))
    await db.commit()
    return {"ok": True}


# ---------- results: the owner and branch admins only ----------
def _avg(values: list[int]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


@router.get("/lesson-surveys/results")
async def results(db: DB, actor: Actor = require("students", "archive"), branch_id: int | None = None,
                  date_from: date | None = None, date_to: date | None = None) -> dict:
    d2 = date_to or today()
    d1 = date_from or d2 - timedelta(days=30)
    if d1 > d2 or (d2 - d1).days > 366:
        raise bad_request("Период — не больше года")
    start, end = local_range(d1, d2)
    q = (select(LessonSurvey, Lesson).join(Lesson, Lesson.id == LessonSurvey.lesson_id)
         .where(Lesson.starts_at >= start, Lesson.starts_at < end).order_by(Lesson.starts_at.desc()).limit(500))
    allowed = actor.branches_for("students", "archive")
    if allowed is not None:
        q = q.where(Lesson.branch_id.in_(allowed))
    if branch_id:
        q = q.where(Lesson.branch_id == branch_id)
    rows = (await db.execute(q)).all()
    ids = [sv.id for sv, _ in rows]
    by_survey: dict[int, list[list]] = {}
    for a in await db.scalars(select(LessonSurveyAnswer).where(LessonSurveyAnswer.survey_id.in_(ids or [-1])).order_by(LessonSurveyAnswer.id)):
        by_survey.setdefault(a.survey_id, []).append(a.answers)
    groups = dict((await db.execute(select(Group.id, Group.name).where(Group.id.in_({l.group_id for _, l in rows if l.group_id} or {-1})))).all())
    tids = {l.actual_teacher_id or l.teacher_id for _, l in rows}
    teachers = dict((await db.execute(select(User.id, User.full_name).where(User.id.in_(tids or {-1})))).all())
    out, per_teacher = [], {}
    for sv, lesson in rows:
        answers = by_survey.get(sv.id, [])
        tid = lesson.actual_teacher_id or lesson.teacher_id
        qs = []
        stars_all: list[int] = []
        for i, qn in enumerate(sv.questions):
            vals = [a[i] for a in answers if i < len(a) and a[i] is not None]
            if qn["kind"] == "stars":
                nums = [v for v in vals if isinstance(v, int)]
                stars_all += nums
                qs.append({"text": qn["text"], "kind": "stars", "avg": _avg(nums), "count": len(nums)})
            else:
                qs.append({"text": qn["text"], "kind": "text", "comments": [str(v) for v in vals]})
        out.append({"survey_id": sv.id, "lesson_id": lesson.id, "at": lesson.starts_at, "branch_id": lesson.branch_id,
                    "group": groups.get(lesson.group_id), "teacher_id": tid, "teacher": teachers.get(tid),
                    "answers": len(answers), "avg": _avg(stars_all), "questions": qs})
        if stars_all:
            p = per_teacher.setdefault(tid, {"teacher_id": tid, "teacher": teachers.get(tid), "lessons": 0, "answers": 0, "stars": []})
            p["lessons"] += 1
            p["answers"] += len(answers)
            p["stars"] += stars_all
    people = [{"teacher_id": p["teacher_id"], "teacher": p["teacher"], "lessons": p["lessons"], "answers": p["answers"],
               "avg": _avg(p["stars"])} for p in per_teacher.values()]
    people.sort(key=lambda p: -(p["avg"] or 0))
    return {"date_from": d1, "date_to": d2, "lessons": out, "teachers": people}
