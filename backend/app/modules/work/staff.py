"""Staff check-in/out and daily reports (Правила для сотрудников), staff training base (ТЗ 15)."""

from datetime import date, time, timedelta

from fastapi import APIRouter
from pydantic import Field
from sqlalchemy import func, select

from app.core.audit import write_audit
from app.core.deps import DB, Actor, require, require_staff
from app.core.errors import bad_request, conflict, not_found
from app.core.schemas import In
from app.models import Attempt, Course, DailyReport, Material, MaterialProgress, StaffCheckin, User, UserBranch
from app.services.clock import at_local, now, today

router = APIRouter(tags=["staff"])


# ---------- check-in ----------
class CheckinIn(In):
    branch_id: int


@router.post("/checkin", status_code=201)
async def check_in(body: CheckinIn, db: DB, actor: Actor = require_staff()) -> dict:
    if body.branch_id not in actor.branch_ids:
        raise bad_request("Это не ваш филиал")
    if await db.scalar(select(StaffCheckin).where(StaffCheckin.user_id == actor.id, StaffCheckin.out_at.is_(None),
                                                  StaffCheckin.in_at >= at_local(today(), time(0)))):
        raise conflict("Вы уже отметили приход")
    c = StaffCheckin(user_id=actor.id, branch_id=body.branch_id, in_at=now())
    db.add(c)
    await db.commit()
    return {"id": c.id, "in_at": c.in_at}


@router.post("/checkout")
async def check_out(db: DB, actor: Actor = require_staff()) -> dict:
    c = await db.scalar(select(StaffCheckin).where(StaffCheckin.user_id == actor.id, StaffCheckin.out_at.is_(None))
                        .order_by(StaffCheckin.id.desc()).limit(1))
    if c is None:
        raise conflict("Сначала отметьте приход")
    c.out_at = now()
    await db.commit()
    return {"id": c.id, "in_at": c.in_at, "out_at": c.out_at}


@router.get("/checkins")
async def checkins(db: DB, actor: Actor = require("staff", "view"), day: date | None = None,
                   branch_id: int | None = None) -> list[dict]:
    d = day or today()
    a = at_local(d, time(0))
    q = (select(StaffCheckin, User.full_name).join(User, User.id == StaffCheckin.user_id)
         .where(StaffCheckin.in_at >= a, StaffCheckin.in_at < a + timedelta(days=1)))
    allowed = actor.branches_for("staff", "view")
    if allowed is not None:
        q = q.where(StaffCheckin.branch_id.in_(allowed))
    if branch_id:
        q = q.where(StaffCheckin.branch_id == branch_id)
    return [{"user_id": c.user_id, "full_name": n, "branch_id": c.branch_id, "in_at": c.in_at, "out_at": c.out_at}
            for c, n in (await db.execute(q.order_by(StaffCheckin.in_at))).all()]


@router.get("/checkin/me")
async def my_checkin(db: DB, actor: Actor = require_staff()) -> dict:
    c = await db.scalar(select(StaffCheckin).where(StaffCheckin.user_id == actor.id, StaffCheckin.in_at >= at_local(today(), time(0)))
                        .order_by(StaffCheckin.id.desc()).limit(1))
    return {"in_at": c.in_at if c else None, "out_at": c.out_at if c else None, "branch_id": c.branch_id if c else None}


# ---------- daily reports ----------
class ReportIn(In):
    text: str = Field(min_length=10, max_length=8000)


@router.put("/daily-report")
async def submit_report(body: ReportIn, db: DB, actor: Actor = require_staff()) -> dict:
    day = today().isoformat()
    r = await db.scalar(select(DailyReport).where(DailyReport.user_id == actor.id, DailyReport.day == day))
    if r is None:
        r = DailyReport(user_id=actor.id, day=day, text=body.text)
        db.add(r)
    else:
        r.text = body.text
    await db.commit()
    return {"day": day}


@router.get("/daily-report")
async def my_report(db: DB, actor: Actor = require_staff()) -> dict:
    day = today().isoformat()
    r = await db.scalar(select(DailyReport).where(DailyReport.user_id == actor.id, DailyReport.day == day))
    return {"day": day, "text": r.text if r else None, "updated_at": r.updated_at if r else None}


@router.get("/daily-reports")
async def reports(db: DB, actor: Actor = require("staff", "view"), day: date | None = None) -> list[dict]:
    d = (day or today()).isoformat()
    q = (select(DailyReport, User.full_name).join(User, User.id == DailyReport.user_id).where(DailyReport.day == d))
    allowed = actor.branches_for("staff", "view")
    if allowed is not None:
        q = q.where(DailyReport.user_id.in_(select(UserBranch.user_id).where(UserBranch.branch_id.in_(allowed))))
    return [{"user_id": r.user_id, "full_name": n, "text": r.text, "updated_at": r.updated_at}
            for r, n in (await db.execute(q.order_by(User.full_name))).all()]


# ---------- training base ----------
class CourseIn(In):
    title: str = Field(min_length=3, max_length=255)
    description: str | None = Field(default=None, max_length=8000)
    role_codes: list[str] = Field(default_factory=list)


class MaterialIn(In):
    kind: str = Field(pattern="^(video|document|test)$")
    title: str = Field(min_length=2, max_length=255)
    url: str | None = Field(default=None, max_length=255)
    body: str | None = Field(default=None, max_length=50_000)
    test_id: int | None = None
    order: int = 0


def _for_me(actor: Actor, c: Course) -> bool:
    return actor.can("training", "edit") or not c.role_codes or bool(set(c.role_codes) & actor.role_codes)


@router.get("/training/courses")
async def courses(db: DB, actor: Actor = require("training", "view")) -> list[dict]:
    rows = [c for c in await db.scalars(select(Course).where(Course.archived_at.is_(None)).order_by(Course.id)) if _for_me(actor, c)]
    out = []
    for c in rows:
        total = await db.scalar(select(func.count()).select_from(Material).where(Material.course_id == c.id,
                                                                                 Material.archived_at.is_(None)))
        done = await db.scalar(select(func.count()).select_from(MaterialProgress).join(Material, Material.id == MaterialProgress.material_id)
                               .where(Material.course_id == c.id, Material.archived_at.is_(None), MaterialProgress.user_id == actor.id))
        out.append({"id": c.id, "title": c.title, "description": c.description, "role_codes": c.role_codes,
                    "materials": total, "done": done})
    return out


@router.post("/training/courses", status_code=201)
async def create_course(body: CourseIn, db: DB, actor: Actor = require("training", "edit")) -> dict:
    c = Course(**body.model_dump())
    db.add(c)
    await db.flush()
    await write_audit(db, actor_id=actor.id, action="training.course_create", entity="course", entity_id=c.id, ip=actor.ip)
    await db.commit()
    return {"id": c.id}


@router.get("/training/courses/{course_id}")
async def course(course_id: int, db: DB, actor: Actor = require("training", "view")) -> dict:
    c = await db.get(Course, course_id)
    if c is None or c.archived_at or not _for_me(actor, c):
        raise not_found("Курс")
    mats = list(await db.scalars(select(Material).where(Material.course_id == c.id, Material.archived_at.is_(None))
                                 .order_by(Material.order, Material.id)))
    prog = {p.material_id: p for p in await db.scalars(select(MaterialProgress).where(
        MaterialProgress.user_id == actor.id, MaterialProgress.material_id.in_([m.id for m in mats] or [-1])))}
    return {"id": c.id, "title": c.title, "description": c.description, "role_codes": c.role_codes,
            "materials": [{"id": m.id, "kind": m.kind, "title": m.title, "url": m.url, "body": m.body, "test_id": m.test_id,
                           "done_at": prog[m.id].done_at if m.id in prog else None,
                           "score": prog[m.id].score if m.id in prog else None} for m in mats]}


@router.post("/training/courses/{course_id}/materials", status_code=201)
async def add_material(course_id: int, body: MaterialIn, db: DB, actor: Actor = require("training", "edit")) -> dict:
    if not await db.get(Course, course_id):
        raise not_found("Курс")
    if body.kind == "test" and not body.test_id:
        raise bad_request("Выберите тест")
    m = Material(course_id=course_id, **body.model_dump())
    db.add(m)
    await db.flush()
    await write_audit(db, actor_id=actor.id, action="training.material_add", entity="material", entity_id=m.id, ip=actor.ip)
    await db.commit()
    return {"id": m.id}


class DoneIn(In):
    attempt_id: int | None = None


@router.post("/training/materials/{material_id}/done")
async def material_done(material_id: int, body: DoneIn, db: DB, actor: Actor = require("training", "view")) -> dict:
    m = await db.get(Material, material_id)
    c = await db.get(Course, m.course_id) if m else None
    if m is None or c is None or not _for_me(actor, c):
        raise not_found("Материал")
    score = None
    if m.kind == "test":
        a = await db.get(Attempt, body.attempt_id) if body.attempt_id else None
        if a is None or a.user_id != actor.id or a.test_id != m.test_id or a.finished_at is None:
            raise bad_request("Сначала пройдите тест")
        score = a.score
    p = await db.scalar(select(MaterialProgress).where(MaterialProgress.user_id == actor.id, MaterialProgress.material_id == m.id))
    if p is None:
        p = MaterialProgress(user_id=actor.id, material_id=m.id, done_at=now(), score=score)
        db.add(p)
    elif score is not None:
        p.score, p.done_at = max(p.score or 0, score), now()
    await db.commit()
    return {"done_at": p.done_at, "score": p.score}


@router.get("/training/progress")
async def progress(db: DB, actor: Actor = require("training", "progress")) -> list[dict]:
    """Admin view: every staff member's progress per course."""
    allowed = actor.branches_for("training", "progress")
    uq = select(User).where(User.kind == "staff", User.is_active.is_(True), User.archived_at.is_(None))
    if allowed is not None:
        uq = uq.where(User.id.in_(select(UserBranch.user_id).where(UserBranch.branch_id.in_(allowed))))
    users = list(await db.scalars(uq.order_by(User.full_name)))
    mats = {m.id: m.course_id for m in await db.scalars(select(Material).where(Material.archived_at.is_(None)))}
    totals: dict[int, int] = {}
    for cid in mats.values():
        totals[cid] = totals.get(cid, 0) + 1
    titles = {c.id: c.title for c in await db.scalars(select(Course).where(Course.archived_at.is_(None)))}
    done: dict[tuple[int, int], int] = {}
    for p in await db.scalars(select(MaterialProgress).where(MaterialProgress.user_id.in_([u.id for u in users] or [-1]))):
        if p.material_id in mats:
            k = (p.user_id, mats[p.material_id])
            done[k] = done.get(k, 0) + 1
    return [{"user_id": u.id, "full_name": u.full_name, "position": u.position,
             "courses": [{"course_id": cid, "title": titles.get(cid), "done": done.get((u.id, cid), 0), "total": t}
                         for cid, t in totals.items() if cid in titles]} for u in users]

