"""Global search (Ctrl+K): students, leads, groups and staff the actor may see."""

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.core.deps import DB, Actor, require_staff
from app.models import Group, Lead, Student, User, UserBranch
from app.modules.crm.service import lead_filter
from app.modules.students.scope import student_filter

router = APIRouter(tags=["search"])


@router.get("/search")
async def search(db: DB, actor: Actor = require_staff(), q: str = Query(min_length=2, max_length=100)) -> dict:
    term = f"%{q.strip()}%"
    digits = "".join(c for c in q if c.isdigit())
    out: dict[str, list] = {}
    if actor.can("students", "view"):
        cond = Student.full_name.ilike(term)
        if len(digits) >= 4:
            cond = cond | Student.phone.contains(digits)
        rows = await db.scalars(select(Student).where(student_filter(actor), Student.archived_at.is_(None), cond).limit(8))
        out["students"] = [{"id": s.id, "title": s.full_name, "status": s.status, "branch_id": s.branch_id} for s in rows]
    if actor.can("crm", "view"):
        cond = Lead.full_name.ilike(term)
        if len(digits) >= 4:
            cond = cond | Lead.phone.contains(digits)
        rows = await db.scalars(select(Lead).where(lead_filter(actor), Lead.archived_at.is_(None), cond).limit(8))
        out["leads"] = [{"id": x.id, "title": x.full_name, "source": x.source, "branch_id": x.branch_id} for x in rows]
    if actor.can("schedule", "view"):
        gq = select(Group).where(Group.archived_at.is_(None), Group.name.ilike(term))
        allowed = actor.branches_for("schedule", "view")
        if actor.is_own_scope("schedule", "view"):
            gq = gq.where(Group.teacher_id == actor.id)
        elif allowed is not None:
            gq = gq.where(Group.branch_id.in_(allowed))
        out["groups"] = [{"id": g.id, "title": g.name, "branch_id": g.branch_id} for g in await db.scalars(gq.limit(8))]
    if actor.can("staff", "view"):
        uq = select(User).where(User.kind == "staff", User.archived_at.is_(None), User.full_name.ilike(term))
        allowed = actor.branches_for("staff", "view")
        if allowed is not None:
            uq = uq.where(User.id.in_(select(UserBranch.user_id).where(UserBranch.branch_id.in_(allowed))))
        rows = await db.scalars(uq.limit(8))
        out["staff"] = [{"id": u.id, "title": u.full_name, "position": u.position} for u in rows]
    return out
