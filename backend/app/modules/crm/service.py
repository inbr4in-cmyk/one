from sqlalchemy import and_, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import Actor
from app.core.errors import forbidden, not_found
from app.core.permissions import NETWORK, OWN
from app.models import Branch, Lead, LeadEvent, Pipeline, Student, StudentGuardian, User, UserBranch, UserRole
from app.models.identity import RolePermission
from app.services.clock import at_local, local, now, today
from app.services.crm import stage_by_code
from app.services.messaging import notify_user


def lead_filter(actor: Actor, action: str = "view"):
    scope = actor.scope("crm", action)
    if scope == NETWORK:
        cond = true()
    elif scope == OWN:
        cond = or_(Lead.owner_id == actor.id, Lead.assignee_id == actor.id, _free(actor))
    else:
        cond = or_(Lead.branch_id.in_(actor.branch_ids or {-1}), Lead.branch_id.is_(None))  # no branch yet: everyone's
    if actor.stage_hidden:
        cond = and_(cond, Lead.stage_id.notin_(actor.stage_hidden))
    if actor.stage_own:
        cond = and_(cond, or_(Lead.stage_id.notin_(actor.stage_own), Lead.owner_id == actor.id, Lead.assignee_id == actor.id,
                              Lead.free_since.is_not(None)))
    return cond


def _free(actor: Actor):
    """A free lead (its manager missed the deadline) is open to every manager of the branch."""
    return and_(Lead.free_since.is_not(None), or_(Lead.branch_id.in_(actor.branch_ids or {-1}), Lead.branch_id.is_(None)))


def stage_editable(actor: Actor, stage_id: int) -> bool:
    return stage_id not in actor.stage_hidden and stage_id not in actor.stage_readonly


async def get_lead_scoped(db: AsyncSession, actor: Actor, lead_id: int, action: str = "view") -> Lead:
    lead = await db.scalar(select(Lead).where(Lead.id == lead_id, lead_filter(actor, action)))
    if lead is None:
        raise not_found("Лид")
    if action != "view" and not stage_editable(actor, lead.stage_id):
        raise forbidden("Лиды на этом этапе вам доступны только для просмотра")
    return lead


async def find_by_phone(db: AsyncSession, phone: str | None, branch_id: int | None = None) -> Lead | None:
    """The newest open lead with this phone (own or parent's); with branch_id — only in that branch."""
    if not phone:
        return None
    q = select(Lead).where(or_(Lead.phone == phone, Lead.parent_phone == phone), Lead.archived_at.is_(None))
    if branch_id is not None:
        q = q.where(Lead.branch_id == branch_id)
    return await db.scalar(q.order_by(Lead.id.desc()).limit(1))


async def find_client_by_phone(db: AsyncSession, phone: str | None) -> Student | None:
    """An existing student, or a student whose parent has this phone."""
    if not phone:
        return None
    s = await db.scalar(select(Student).where(Student.phone == phone, Student.archived_at.is_(None)))
    if s:
        return s
    return await db.scalar(select(Student).join(StudentGuardian, StudentGuardian.student_id == Student.id)
                           .join(User, User.id == StudentGuardian.user_id).where(User.phone == phone))


async def merge_into_student(db: AsyncSession, lead: Lead, student: Student, actor_id: int | None) -> None:
    """The person behind the lead turned out to be an existing student (or a student's parent): the lead goes to the
    archive with a note, and its Instagram/WhatsApp chats now belong to the student's card. Nothing is deleted."""
    from app.models import Conversation, ExternalContact

    for c in await db.scalars(select(ExternalContact).where(ExternalContact.lead_id == lead.id)):
        c.lead_id, c.student_id = None, student.id
        for conv in await db.scalars(select(Conversation).where(Conversation.contact_id == c.id)):
            conv.branch_id = student.branch_id
    t = now()
    lead.archived_at = lead.last_activity_at = t
    db.add(LeadEvent(lead_id=lead.id, at=t, kind="note", text=f"Это ученик школы: {student.full_name}. Лид объединён с его карточкой",
                     actor_id=actor_id, meta={"student_id": student.id}))


async def default_branch_id(db: AsyncSession) -> int:
    return await db.scalar(select(Branch.id).where(Branch.archived_at.is_(None)).order_by(Branch.id))


async def crm_people(db: AsyncSession, branch_id: int | None, module: str = "inbox", action: str = "view") -> list[int]:
    """Staff of the branch who work with leads — they get notified about new ones. No branch yet: staff of every branch."""
    q = (select(UserBranch.user_id).join(UserRole, UserRole.user_id == UserBranch.user_id)
         .join(RolePermission, RolePermission.role_id == UserRole.role_id)
         .join(User, User.id == UserBranch.user_id)
         .where(RolePermission.module == module, RolePermission.action == action,
                User.is_active.is_(True), User.archived_at.is_(None)))
    if branch_id is not None:
        q = q.where(UserBranch.branch_id == branch_id)
    return list(await db.scalars(q.distinct()))


async def set_branch(db: AsyncSession, lead: Lead, branch_id: int, actor_id: int | None) -> None:
    """The branch is picked (or changed): the lead and its Instagram/WhatsApp chats move there, the step is in the history."""
    if lead.branch_id == branch_id:
        return
    from app.models import Conversation, ExternalContact

    b = await db.get(Branch, branch_id)
    if b is None or b.archived_at is not None:
        raise not_found("Филиал")
    lead.branch_id = branch_id
    for conv in await db.scalars(select(Conversation).join(ExternalContact, ExternalContact.id == Conversation.contact_id)
                                 .where(ExternalContact.lead_id == lead.id)):
        conv.branch_id = branch_id
    db.add(LeadEvent(lead_id=lead.id, at=now(), kind="note", text=f"Филиал: {b.name}", actor_id=actor_id, meta={"branch_id": branch_id}))


async def create_lead(db: AsyncSession, *, full_name: str, phone: str | None, branch_id: int | None, source: str,
                      owner_id: int | None, assignee_id: int | None = None, pipeline: str = "main", stage: str = "new",
                      notify: bool = True, contacted_on=None, **extra) -> Lead:
    """contacted_on: the day the person really got in touch, when the card is entered later (it becomes the lead's
    date in the funnel and reports; the history keeps who entered it and when)."""
    st = await stage_by_code(db, pipeline, stage)
    lead = Lead(full_name=full_name, phone=phone, branch_id=branch_id, pipeline_id=st.pipeline_id, stage_id=st.id,
                stage_changed_at=now(), source=source, owner_id=owner_id, assignee_id=assignee_id or owner_id,
                last_activity_at=now(), **extra)
    db.add(lead)
    await db.flush()
    note = ""
    if contacted_on and contacted_on < today():
        lead.created_at = at_local(contacted_on, local(now()).time().replace(microsecond=0))
        note = f" · дата обращения {contacted_on:%d.%m.%Y}"
    db.add(LeadEvent(lead_id=lead.id, at=now(), kind="created", text=f"Источник: {source}{note}", actor_id=owner_id, meta={}))
    if notify:
        targets = [assignee_id] if assignee_id else await crm_people(db, branch_id, "crm")
        for uid in targets:
            if uid and uid != owner_id:
                await notify_user(db, uid, "lead", f"Новый лид: {full_name}", link=f"/crm/leads/{lead.id}",
                                  meta_={"source": source})
    return lead


async def pipeline_id(db: AsyncSession, code: str) -> int:
    return await db.scalar(select(Pipeline.id).where(Pipeline.code == code))
