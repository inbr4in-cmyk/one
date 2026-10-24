"""Platform rules and recording consent with versions, and the complaints procedure (Правила платформы)."""

from datetime import datetime, timedelta

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.audit import write_audit
from app.core.deps import DB, Actor, CurrentActor, require
from app.core.errors import bad_request, conflict, forbidden, not_found
from app.models import Complaint, Consent, DocumentVersion, Role, Student, StudentGuardian, User, UserBranch, UserRole
from app.models.identity import UserKind
from app.modules.crm.service import crm_people
from app.services.clock import local, now
from app.services.messaging import notify_user

router = APIRouter(tags=["compliance"])


def add_business_days(start: datetime, days: int) -> datetime:
    d = local(start)
    while days:
        d += timedelta(days=1)
        if d.weekday() < 5:
            days -= 1
    return d


# ---------- documents ----------
class DocIn(BaseModel):
    kind: str = Field(pattern="^(rules|recording)$")
    version: str = Field(min_length=1, max_length=16)
    title: str = Field(min_length=3, max_length=255)
    body: str = Field(min_length=10, max_length=100_000)
    effective_from: datetime


async def current_doc(db: DB, kind: str) -> DocumentVersion | None:
    return await db.scalar(select(DocumentVersion).where(DocumentVersion.kind == kind, DocumentVersion.effective_from <= now())
                           .order_by(DocumentVersion.effective_from.desc()).limit(1))


@router.get("/documents/{kind}")
async def get_document(kind: str, db: DB, actor: CurrentActor) -> dict:
    doc = await current_doc(db, kind)
    if doc is None:
        raise not_found("Документ")
    upcoming = await db.scalar(select(DocumentVersion).where(DocumentVersion.kind == kind, DocumentVersion.effective_from > now())
                               .order_by(DocumentVersion.effective_from).limit(1))
    return {"id": doc.id, "kind": doc.kind, "version": doc.version, "title": doc.title, "body": doc.body,
            "effective_from": doc.effective_from,
            "upcoming": {"version": upcoming.version, "effective_from": upcoming.effective_from} if upcoming else None}


@router.post("/documents", status_code=201)
async def publish_document(body: DocIn, db: DB, actor: Actor = require("settings", "edit")) -> dict:
    """New rules are announced at least 7 days before they apply (Правила, «Изменения правил»)."""
    if body.kind == "rules" and body.effective_from < now() + timedelta(days=7) and await current_doc(db, "rules"):
        raise bad_request("Изменения правил вступают в силу не раньше чем через 7 дней")
    if await db.scalar(select(DocumentVersion).where(DocumentVersion.kind == body.kind, DocumentVersion.version == body.version)):
        raise conflict("Такая версия уже есть")
    d = DocumentVersion(**body.model_dump())
    db.add(d)
    await db.flush()
    await write_audit(db, actor_id=actor.id, action="document.publish", entity="document", entity_id=d.id, ip=actor.ip,
                      after={"kind": d.kind, "version": d.version, "effective_from": d.effective_from.isoformat()})
    await db.commit()
    return {"id": d.id}


class AcceptIn(BaseModel):
    document_id: int
    student_id: int | None = None  # a parent signs the recording consent for a child


@router.post("/consents", status_code=201)
async def accept(body: AcceptIn, request: Request, db: DB, actor: CurrentActor) -> dict:
    doc = await db.get(DocumentVersion, body.document_id)
    if doc is None or doc.effective_from > now() + timedelta(days=31):
        raise not_found("Документ")
    if body.student_id is not None:
        if actor.user.kind != UserKind.PARENT or not await db.scalar(select(StudentGuardian).where(
                StudentGuardian.student_id == body.student_id, StudentGuardian.user_id == actor.id)):
            raise forbidden("Согласие за ребёнка даёт его родитель")
    c = Consent(user_id=actor.id, student_id=body.student_id, document_id=doc.id, accepted_at=now(), ip=actor.ip,
                user_agent=(request.headers.get("user-agent") or "")[:255])
    db.add(c)
    if doc.kind == "rules" and body.student_id is None:
        actor.user.rules_accepted_version = doc.version
    await write_audit(db, actor_id=actor.id, action=f"consent.{doc.kind}", entity="document", entity_id=doc.id, ip=actor.ip,
                      after={"version": doc.version, "student_id": body.student_id})
    await db.commit()
    return {"accepted_at": c.accepted_at, "version": doc.version}


@router.post("/consents/{consent_id}/revoke", status_code=204)
async def revoke(consent_id: int, db: DB, actor: CurrentActor) -> None:
    c = await db.get(Consent, consent_id)
    if c is None or c.user_id != actor.id or c.revoked_at:
        raise not_found("Согласие")
    c.revoked_at = now()
    await write_audit(db, actor_id=actor.id, action="consent.revoke", entity="consent", entity_id=c.id, ip=actor.ip)
    await db.commit()


@router.get("/consents/status")
async def consent_status(db: DB, actor: Actor = require("students", "view"), branch_id: int | None = None) -> list[dict]:
    """Who still hasn't given the recording consent (admins chase them)."""
    doc = await current_doc(db, "recording")
    if doc is None:
        return []
    q = select(Student).where(Student.archived_at.is_(None), Student.status == "active")
    allowed = actor.branches_for("students", "view")
    if allowed is not None:
        q = q.where(Student.branch_id.in_(allowed))
    if branch_id:
        q = q.where(Student.branch_id == branch_id)
    signed = set(await db.scalars(select(Consent.student_id).where(Consent.document_id == doc.id, Consent.revoked_at.is_(None))))
    signed_self = set(await db.scalars(select(Consent.user_id).where(Consent.document_id == doc.id, Consent.student_id.is_(None),
                                                                    Consent.revoked_at.is_(None))))
    return [{"student_id": s.id, "full_name": s.full_name, "branch_id": s.branch_id}
            for s in await db.scalars(q.limit(2000)) if s.id not in signed and s.user_id not in signed_self]


# ---------- complaints ----------
async def owner_ids(db: DB) -> set[int]:
    return set(await db.scalars(select(UserRole.user_id).join(Role, Role.id == UserRole.role_id)
                                .join(User, User.id == UserRole.user_id)
                                .where(Role.code == "owner", User.is_active.is_(True))))

class ComplaintIn(BaseModel):
    subject: str = Field(min_length=3, max_length=255)
    body: str = Field(min_length=10, max_length=8000)
    branch_id: int | None = None
    against_user_id: int | None = None
    file_url: str | None = Field(default=None, max_length=255)


def _view(c: Complaint, for_author: bool) -> dict:
    d = {"id": c.id, "subject": c.subject, "body": c.body, "status": c.status, "created_at": c.created_at,
         "acknowledged_at": c.acknowledged_at, "due_at": c.due_at, "answer": c.answer, "answered_at": c.answered_at,
         "branch_id": c.branch_id, "file_url": c.file_url}
    if not for_author:
        d |= {"author_id": c.author_id, "against_user_id": c.against_user_id,
              "overdue": c.status not in ("answered", "closed") and c.due_at < now()}
    return d


async def _author_branch(db: DB, actor: Actor) -> int | None:
    if actor.is_staff:
        return await db.scalar(select(UserBranch.branch_id).where(UserBranch.user_id == actor.id).limit(1))
    if actor.user.kind == UserKind.STUDENT:
        return await db.scalar(select(Student.branch_id).where(Student.user_id == actor.id).limit(1))
    return await db.scalar(select(Student.branch_id).join(StudentGuardian, StudentGuardian.student_id == Student.id)
                           .where(StudentGuardian.user_id == actor.id).limit(1))


def _handlers_filter(actor: Actor):
    """Complaints go to the administration; the person complained about never sees them."""
    allowed = actor.branches_for("complaints", "view")
    conds = [(Complaint.against_user_id.is_(None)) | (Complaint.against_user_id != actor.id)]
    if allowed is not None:
        conds.append(Complaint.branch_id.in_(allowed))
    return conds


@router.post("/complaints", status_code=201)
async def file_complaint(body: ComplaintIn, db: DB, actor: CurrentActor) -> dict:
    branch = body.branch_id or await _author_branch(db, actor)
    c = Complaint(author_id=actor.id, branch_id=branch, subject=body.subject, body=body.body,
                  against_user_id=body.against_user_id, file_url=body.file_url, status="new",
                  due_at=add_business_days(now(), 3))
    db.add(c)
    await db.flush()
    handlers = set(await crm_people(db, branch, "complaints", "view")) if branch else await owner_ids(db)
    for uid in handlers - {body.against_user_id, actor.id}:
        await notify_user(db, uid, "complaint", f"Новая жалоба: {c.subject}", body="Подтвердите получение в течение 24 часов",
                          link=f"/complaints/{c.id}")
    await write_audit(db, actor_id=actor.id, action="complaint.create", entity="complaint", entity_id=c.id, branch_id=branch,
                      ip=actor.ip)
    await db.commit()
    return _view(c, True)


@router.get("/complaints/my")
async def my_complaints(db: DB, actor: CurrentActor) -> list[dict]:
    return [_view(c, True) for c in await db.scalars(select(Complaint).where(Complaint.author_id == actor.id)
                                                     .order_by(Complaint.id.desc()))]


@router.get("/complaints")
async def complaints(db: DB, actor: Actor = require("complaints", "view"), status: str | None = None) -> list[dict]:
    q = select(Complaint).where(*_handlers_filter(actor))
    if status:
        q = q.where(Complaint.status == status)
    return [_view(c, False) for c in await db.scalars(q.order_by(Complaint.due_at).limit(500))]


class ComplaintAction(BaseModel):
    action: str = Field(pattern="^(acknowledge|investigate|answer|close|appeal)$")
    answer: str | None = Field(default=None, max_length=8000)


@router.post("/complaints/{complaint_id}")
async def act(complaint_id: int, body: ComplaintAction, db: DB, actor: CurrentActor) -> dict:
    c = await db.get(Complaint, complaint_id)
    if c is None:
        raise not_found("Жалоба")
    if body.action == "appeal":
        # The author can appeal an answer to the operations director (owner).
        if c.author_id != actor.id or c.status != "answered":
            raise forbidden("Обжаловать можно полученный ответ")
        c.status = "appealed"
        c.due_at = add_business_days(now(), 3)
        for uid in await owner_ids(db):
            await notify_user(db, uid, "complaint", f"Обжалование: {c.subject}", link=f"/complaints/{c.id}")
    else:
        if not actor.can("complaints", "answer"):
            raise forbidden()
        if not await db.scalar(select(Complaint.id).where(Complaint.id == c.id, *_handlers_filter(actor))):
            raise not_found("Жалоба")
        if c.status == "appealed" and not actor.is_owner:
            raise forbidden("Обжалование рассматривает операционный директор")
        if body.action == "acknowledge":
            c.acknowledged_at = c.acknowledged_at or now()
            c.status = "acknowledged" if c.status == "new" else c.status
            await notify_user(db, c.author_id, "complaint", "Жалоба получена",
                              body=f"Ответим до {local(c.due_at).strftime('%d.%m')}", link=f"/complaints/{c.id}")
        elif body.action == "investigate":
            # A check (e.g. lesson video) extends the deadline to 7 business days; the author is told.
            c.status = "investigating"
            c.acknowledged_at = c.acknowledged_at or now()
            c.due_at = add_business_days(c.created_at, 7)
            await notify_user(db, c.author_id, "complaint", "Жалоба на проверке",
                              body=f"Нужна проверка, ответ до {local(c.due_at).strftime('%d.%m')}", link=f"/complaints/{c.id}")
        elif body.action == "answer":
            if not body.answer or len(body.answer.strip()) < 5:
                raise bad_request("Напишите ответ")
            c.status, c.answer, c.answered_by, c.answered_at = "answered", body.answer.strip(), actor.id, now()
            c.acknowledged_at = c.acknowledged_at or now()
            await notify_user(db, c.author_id, "complaint", f"Ответ на жалобу: {c.subject}", body=c.answer[:140],
                              link=f"/complaints/{c.id}")
        elif body.action == "close":
            c.status = "closed"
    await write_audit(db, actor_id=actor.id, action=f"complaint.{body.action}", entity="complaint", entity_id=c.id,
                      branch_id=c.branch_id, ip=actor.ip)
    await db.commit()
    return _view(c, c.author_id == actor.id)
