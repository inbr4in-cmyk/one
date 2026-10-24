from sqlalchemy import or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import Actor
from app.core.errors import not_found
from app.core.permissions import NETWORK, OWN
from app.models import Branch, Lead, LeadEvent, Pipeline, Student, StudentGuardian, User, UserBranch, UserRole
from app.models.identity import RolePermission
from app.services.clock import now
from app.services.crm import stage_by_code
from app.services.messaging import notify_user


def lead_filter(actor: Actor, action: str = "view"):
    scope = actor.scope("crm", action)
    if scope == NETWORK:
        return true()
    if scope == OWN:
        return or_(Lead.owner_id == actor.id, Lead.assignee_id == actor.id)
    return Lead.branch_id.in_(actor.branch_ids or {-1})


async def get_lead_scoped(db: AsyncSession, actor: Actor, lead_id: int, action: str = "view") -> Lead:
    lead = await db.scalar(select(Lead).where(Lead.id == lead_id, lead_filter(actor, action)))
    if lead is None:
        raise not_found("Лид")
    return lead


async def find_by_phone(db: AsyncSession, phone: str | None) -> Lead | None:
    if not phone:
        return None
    return await db.scalar(select(Lead).where(or_(Lead.phone == phone, Lead.parent_phone == phone), Lead.archived_at.is_(None))
                           .order_by(Lead.id.desc()))


async def find_client_by_phone(db: AsyncSession, phone: str | None) -> Student | None:
    """An existing student, or a student whose parent has this phone."""
    if not phone:
        return None
    s = await db.scalar(select(Student).where(Student.phone == phone, Student.archived_at.is_(None)))
    if s:
        return s
    return await db.scalar(select(Student).join(StudentGuardian, StudentGuardian.student_id == Student.id)
                           .join(User, User.id == StudentGuardian.user_id).where(User.phone == phone))


async def default_branch_id(db: AsyncSession) -> int:
    return await db.scalar(select(Branch.id).where(Branch.archived_at.is_(None)).order_by(Branch.id))


async def crm_people(db: AsyncSession, branch_id: int, module: str = "inbox", action: str = "view") -> list[int]:
    """Staff of the branch who work with leads — they get notified about new ones."""
    rows = await db.scalars(
        select(UserBranch.user_id).join(UserRole, UserRole.user_id == UserBranch.user_id)
        .join(RolePermission, RolePermission.role_id == UserRole.role_id)
        .join(User, User.id == UserBranch.user_id)
        .where(UserBranch.branch_id == branch_id, RolePermission.module == module, RolePermission.action == action,
               User.is_active.is_(True), User.archived_at.is_(None))
        .distinct()
    )
    return list(rows)


async def create_lead(db: AsyncSession, *, full_name: str, phone: str | None, branch_id: int, source: str,
                      owner_id: int | None, assignee_id: int | None = None, pipeline: str = "main", stage: str = "new",
                      notify: bool = True, **extra) -> Lead:
    st = await stage_by_code(db, pipeline, stage)
    lead = Lead(full_name=full_name, phone=phone, branch_id=branch_id, pipeline_id=st.pipeline_id, stage_id=st.id,
                stage_changed_at=now(), source=source, owner_id=owner_id, assignee_id=assignee_id or owner_id,
                last_activity_at=now(), **extra)
    db.add(lead)
    await db.flush()
    db.add(LeadEvent(lead_id=lead.id, at=now(), kind="created", text=f"Источник: {source}", actor_id=owner_id, meta={}))
    if notify:
        targets = [assignee_id] if assignee_id else await crm_people(db, branch_id, "crm")
        for uid in targets:
            if uid and uid != owner_id:
                await notify_user(db, uid, "lead", f"Новый лид: {full_name}", link=f"/crm/leads/{lead.id}",
                                  meta_={"source": source})
    return lead


async def pipeline_id(db: AsyncSession, code: str) -> int:
    return await db.scalar(select(Pipeline.id).where(Pipeline.code == code))
