"""Student and parent cabinet (ТЗ 16.6, 16.7): the same API serves the web cabinet and the Flutter app."""

from datetime import date, datetime, time, timedelta

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.core.deps import DB, CurrentActor
from app.core.errors import bad_request, conflict, forbidden, not_found
from app.models import (
    Attempt, Attendance, Branch, Group, GroupMember, Homework, HomeworkSubmission, Lesson, LessonRating, Level, Payment,
    Room, Test, User,
)
from app.models.identity import UserKind
from app.models.learning import AttendanceStatus, LessonStatus
from app.modules.portal.access import my_students, portal_student
from app.services import coins as coin_svc
from app.services import files
from app.services.clock import at_local, now, today

router = APIRouter(prefix="/portal", tags=["portal"])


def _portal_only(actor) -> None:
    if actor.user.kind not in (UserKind.STUDENT, UserKind.PARENT):
        raise forbidden("Кабинет ученика и родителя")


async def _groups(db: DB, student_id: int) -> list[dict]:
    rows = (await db.execute(
        select(Group, Level.name, User.full_name).join(GroupMember, GroupMember.group_id == Group.id)
        .outerjoin(Level, Level.id == Group.level_id).outerjoin(User, User.id == Group.teacher_id)
        .where(GroupMember.student_id == student_id, GroupMember.left_on.is_(None)))).all()
    return [{"id": g.id, "name": g.name, "level": lv, "teacher": t, "teacher_id": g.teacher_id, "chat_id": g.chat_id}
            for g, lv, t in rows]


@router.get("/me")
async def me(db: DB, actor: CurrentActor) -> dict:
    _portal_only(actor)
    out = []
    for s in await my_students(db, actor):
        branch = await db.get(Branch, s.branch_id)
        level = await db.get(Level, s.level_id) if s.level_id else None
        out.append({"id": s.id, "full_name": s.full_name, "photo_url": s.photo_url, "status": s.status,
                    "branch": {"id": branch.id, "name": branch.name, "phone": branch.phone, "address": branch.address},
                    "level": level.name if level else None, "lessons_left": s.lessons_left, "money_balance": s.money_balance,
                    "debt": s.lessons_left < 0, "blocked": s.access_blocked_at is not None, "stars": s.stars,
                    "coins": await coin_svc.balance(db, s.id), "groups": await _groups(db, s.id)})
    return {"kind": actor.user.kind, "full_name": actor.user.full_name, "children": out}


async def _lessons(db: DB, student_id: int, start: datetime, end: datetime) -> list[dict]:
    group_ids = select(GroupMember.group_id).where(GroupMember.student_id == student_id, GroupMember.left_on.is_(None))
    rows = (await db.execute(
        select(Lesson, Group.name, Room.name, User.full_name).outerjoin(Group, Group.id == Lesson.group_id)
        .join(Room, Room.id == Lesson.room_id)
        .join(User, User.id == func.coalesce(Lesson.actual_teacher_id, Lesson.teacher_id))
        .where((Lesson.group_id.in_(group_ids)) | (Lesson.student_id == student_id),
               Lesson.starts_at >= start, Lesson.starts_at < end).order_by(Lesson.starts_at))).all()
    return [{"id": lsn.id, "starts_at": lsn.starts_at, "ends_at": lsn.ends_at, "group": g, "room": r, "teacher": t,
             "status": lsn.status, "cancel_reason": lsn.cancel_reason, "topic": lsn.topic} for lsn, g, r, t in rows]


@router.get("/students/{student_id}/schedule")
async def schedule(student_id: int, db: DB, actor: CurrentActor, start: date | None = None, days: int = 14) -> list[dict]:
    s = await portal_student(db, actor, student_id, allow_blocked=True)
    d = start or today()
    return await _lessons(db, s.id, at_local(d, time(0)), at_local(d + timedelta(days=min(days, 62)), time(0)))


@router.get("/students/{student_id}/attendance")
async def attendance(student_id: int, db: DB, actor: CurrentActor, limit: int = 50) -> dict:
    s = await portal_student(db, actor, student_id)
    rows = (await db.execute(
        select(Attendance, Lesson.starts_at, Group.name, LessonRating.stars).join(Lesson, Lesson.id == Attendance.lesson_id)
        .outerjoin(Group, Group.id == Lesson.group_id)
        .outerjoin(LessonRating, (LessonRating.lesson_id == Lesson.id) & (LessonRating.student_id == s.id))
        .where(Attendance.student_id == s.id).order_by(Lesson.starts_at.desc()).limit(min(limit, 200)))).all()
    items = [{"lesson_id": a.lesson_id, "at": at, "group": g, "status": a.status, "grade": a.grade, "comment": a.comment,
              "stars": a.stars, "charged": a.charged, "my_rating": r} for a, at, g, r in rows]
    month_start = at_local(today().replace(day=1), time(0))
    month = [i for i in items if i["at"] >= month_start]
    present = sum(1 for i in month if i["status"] in (AttendanceStatus.PRESENT, AttendanceStatus.LATE))
    return {"items": items, "month": {"lessons": len(month), "present": present,
                                      "rate": round(present / len(month) * 100) if month else None}}


@router.get("/students/{student_id}/homework")
async def homework(student_id: int, db: DB, actor: CurrentActor) -> list[dict]:
    s = await portal_student(db, actor, student_id)
    group_ids = select(GroupMember.group_id).where(GroupMember.student_id == s.id, GroupMember.left_on.is_(None))
    rows = (await db.execute(
        select(Homework, HomeworkSubmission).outerjoin(HomeworkSubmission, (HomeworkSubmission.homework_id == Homework.id)
                                                       & (HomeworkSubmission.student_id == s.id))
        .where(Homework.group_id.in_(group_ids), Homework.archived_at.is_(None))
        .order_by(Homework.id.desc()).limit(100))).all()
    return [{"id": h.id, "title": h.title, "body": h.body, "due_at": h.due_at,
             "status": sub.status if sub else "assigned", "grade": sub.grade if sub else None,
             "teacher_comment": sub.teacher_comment if sub else None, "answer": sub.answer if sub else None,
             "file_url": files.signed_url(sub.file_url) if sub else None} for h, sub in rows]


class SubmitIn(BaseModel):
    student_id: int
    answer: str | None = Field(default=None, max_length=8000)
    file_key: str | None = None


@router.post("/homework/{homework_id}/submit")
async def submit(homework_id: int, body: SubmitIn, db: DB, actor: CurrentActor) -> dict:
    if actor.user.kind != UserKind.STUDENT:
        raise forbidden("Домашнее задание сдаёт ученик")
    s = await portal_student(db, actor, body.student_id)
    h = await db.get(Homework, homework_id)
    in_group = h and await db.scalar(select(GroupMember.id).where(GroupMember.group_id == h.group_id,
                                                                  GroupMember.student_id == s.id, GroupMember.left_on.is_(None)))
    if not in_group:
        raise not_found("Задание")
    if not (body.answer and body.answer.strip()) and not body.file_key:
        raise bad_request("Добавьте ответ или файл")
    if body.file_key and not files.path_of(body.file_key):
        raise bad_request("Файл не найден")
    sub = await db.scalar(select(HomeworkSubmission).where(HomeworkSubmission.homework_id == h.id,
                                                           HomeworkSubmission.student_id == s.id))
    if sub and sub.status == "checked":
        raise conflict("Задание уже проверено")
    if sub is None:
        sub = HomeworkSubmission(homework_id=h.id, student_id=s.id)
        db.add(sub)
    sub.status, sub.answer, sub.file_url = "submitted", (body.answer or "").strip() or None, body.file_key
    await db.commit()
    return {"status": sub.status}


@router.get("/students/{student_id}/payments")
async def payments(student_id: int, db: DB, actor: CurrentActor) -> dict:
    """Parents see payments and the balance even when access is blocked — that's how they unblock it."""
    s = await portal_student(db, actor, student_id, allow_blocked=True)
    rows = await db.scalars(select(Payment).where(Payment.student_id == s.id).order_by(Payment.paid_at.desc()).limit(100))
    level = await db.get(Level, s.level_id) if s.level_id else None
    return {"lessons_left": s.lessons_left, "money_balance": s.money_balance, "debt_lessons": max(0, -s.lessons_left),
            "lesson_price": s.balance_lesson_price or (level.lesson_price if level else None),
            "blocked": s.access_blocked_at is not None,
            "items": [{"id": p.id, "paid_at": p.paid_at, "category": p.category, "amount": p.amount, "lessons": p.lessons,
                       "method": p.method, "refunded": p.refunded, "note": p.note} for p in rows]}


@router.get("/students/{student_id}/tests")
async def tests(student_id: int, db: DB, actor: CurrentActor) -> list[dict]:
    s = await portal_student(db, actor, student_id)
    rows = (await db.execute(select(Attempt, Test.title, Test.kind, Test.max_score).join(Test, Test.id == Attempt.test_id)
                             .where(Attempt.student_id == s.id, Attempt.finished_at.is_not(None))
                             .order_by(Attempt.finished_at.desc()))).all()
    return [{"id": a.id, "title": t, "kind": k, "score": a.score, "max_score": m, "finished_at": a.finished_at}
            for a, t, k, m in rows]


class RateIn(BaseModel):
    student_id: int
    stars: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=1000)


@router.post("/lessons/{lesson_id}/rate", status_code=201)
async def rate(lesson_id: int, body: RateIn, db: DB, actor: CurrentActor) -> dict:
    """Only a lesson the child actually attended, within 7 days."""
    s = await portal_student(db, actor, body.student_id)
    lesson = await db.get(Lesson, lesson_id)
    att = await db.scalar(select(Attendance).where(Attendance.lesson_id == lesson_id, Attendance.student_id == s.id))
    if lesson is None or att is None or lesson.status != LessonStatus.DONE or \
            att.status not in (AttendanceStatus.PRESENT, AttendanceStatus.LATE):
        raise not_found("Урок")
    if lesson.starts_at < now() - timedelta(days=7):
        raise conflict("Оценить урок можно в течение 7 дней")
    r = await db.scalar(select(LessonRating).where(LessonRating.lesson_id == lesson_id, LessonRating.student_id == s.id))
    if r is None:
        r = LessonRating(lesson_id=lesson_id, student_id=s.id, user_id=actor.id, stars=body.stars, comment=body.comment)
        db.add(r)
    else:
        r.stars, r.comment, r.user_id = body.stars, body.comment, actor.id
    await db.commit()
    return {"stars": r.stars}
