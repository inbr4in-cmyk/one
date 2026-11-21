"""Platform rules and recording consent with versions, and the complaints procedure (Правила платформы)."""

from datetime import datetime, timedelta
from urllib.parse import urlparse

from fastapi import APIRouter, Request
from pydantic import Field
from sqlalchemy import select

from app.core.audit import write_audit
from app.core.deps import DB, Actor, CurrentActor, ensure_staff_mfa, require
from app.core.ratelimit import hit
from app.core.errors import bad_request, conflict, forbidden, not_found
from app.core.schemas import In
from app.models import (
    Complaint, Consent, DocumentVersion, Role, Student, StudentGuardian, User, UserBranch, UserDoc, UserDocAccept, UserRole,
)
from app.models.identity import UserKind
from app.modules.crm.service import crm_people
from app.services.clock import local, now
from app.services import files
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
class DocIn(In):
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


class AcceptIn(In):
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


@router.get("/consents/my")
async def my_consents(db: DB, actor: CurrentActor) -> list[dict]:
    rows = (await db.execute(select(Consent, DocumentVersion).join(DocumentVersion, DocumentVersion.id == Consent.document_id)
                             .where(Consent.user_id == actor.id).order_by(Consent.id.desc()))).all()
    return [{"id": c.id, "document_id": d.id, "kind": d.kind, "version": d.version, "student_id": c.student_id,
             "accepted_at": c.accepted_at, "revoked_at": c.revoked_at} for c, d in rows]


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


# ---------- files for kinds of users (owner, 21.11.2026) ----------
MAX_USER_DOCS = 2
PORTAL_AUDIENCES = {"parent": "Родители", "student": "Ученики"}


class UserDocIn(In):
    audience: str = Field(min_length=1, max_length=72)
    title: str = Field(min_length=2, max_length=255)
    file_key: str = Field(min_length=8, max_length=80)
    file_name: str = Field(min_length=1, max_length=255)


async def _audiences(db: DB) -> dict[str, str]:
    """A staff role, parents or students: code → title."""
    roles = (await db.execute(select(Role.code, Role.name).where(Role.archived_at.is_(None),
                                                                  Role.code.not_in(("parent", "student"))).order_by(Role.id))).all()
    return {**{code: name for code, name in roles}, **PORTAL_AUDIENCES}


def _my_audiences(actor) -> set[str]:
    if actor.user.kind == UserKind.PARENT:
        return {"parent"}
    if actor.user.kind == UserKind.STUDENT:
        return {"student"}
    return set(actor.role_codes) - set(PORTAL_AUDIENCES)


def _doc_out(d: UserDoc) -> dict:
    return {"id": d.id, "audience": d.audience, "title": d.title, "file_name": d.file_name,
            "url": files.signed_url(d.file_key, ttl=3600, name=d.file_name), "created_at": d.created_at}


@router.get("/user-docs")
async def user_docs(db: DB, actor: Actor = require("settings", "view")) -> dict:
    docs = list(await db.scalars(select(UserDoc).where(UserDoc.archived_at.is_(None)).order_by(UserDoc.id)))
    counts: dict[int, int] = {}
    for doc_id in await db.scalars(select(UserDocAccept.doc_id).where(UserDocAccept.doc_id.in_([d.id for d in docs] or [-1]))):
        counts[doc_id] = counts.get(doc_id, 0) + 1
    return {"audiences": [{"code": c, "name": n} for c, n in (await _audiences(db)).items()], "max": MAX_USER_DOCS,
            "docs": [{**_doc_out(d), "accepted": counts.get(d.id, 0)} for d in docs]}


@router.post("/user-docs", status_code=201)
async def add_user_doc(body: UserDocIn, db: DB, actor: Actor = require("settings", "edit")) -> dict:
    if body.audience not in await _audiences(db):
        raise bad_request("Выберите, для кого файл")
    if files.path_of(body.file_key) is None:
        raise bad_request("Файл не найден — загрузите его ещё раз")
    live = len(list(await db.scalars(select(UserDoc.id).where(UserDoc.audience == body.audience, UserDoc.archived_at.is_(None)))))
    if live >= MAX_USER_DOCS:
        raise bad_request(f"Для одного типа пользователей — не больше {MAX_USER_DOCS} файлов. Удалите старый файл")
    d = UserDoc(audience=body.audience, title=body.title.strip(), file_key=body.file_key, file_name=body.file_name, created_by=actor.id)
    db.add(d)
    await db.flush()
    await write_audit(db, actor_id=actor.id, action="user_doc.add", entity="user_doc", entity_id=d.id, ip=actor.ip,
                      after={"audience": d.audience, "title": d.title, "file": d.file_name})
    await db.commit()
    return _doc_out(d)


@router.delete("/user-docs/{doc_id}", status_code=204)
async def remove_user_doc(doc_id: int, db: DB, actor: Actor = require("settings", "edit")) -> None:
    """The file is no longer shown to anybody; the journal keeps who accepted it."""
    d = await db.get(UserDoc, doc_id)
    if d is None or d.archived_at is not None:
        raise not_found("Файл")
    d.archived_at = now()
    await write_audit(db, actor_id=actor.id, action="user_doc.remove", entity="user_doc", entity_id=d.id, ip=actor.ip,
                      before={"audience": d.audience, "title": d.title})
    await db.commit()


@router.get("/user-docs/pending")
async def pending_user_docs(db: DB, actor: CurrentActor) -> list[dict]:
    """Files of my kind of user that I have not accepted yet. Asked once: an accepted file never comes back."""
    mine = _my_audiences(actor)
    if not mine:
        return []
    done = select(UserDocAccept.doc_id).where(UserDocAccept.user_id == actor.id)
    docs = await db.scalars(select(UserDoc).where(UserDoc.audience.in_(mine), UserDoc.archived_at.is_(None),
                                                  UserDoc.id.not_in(done)).order_by(UserDoc.id))
    return [_doc_out(d) for d in docs]


class UserDocAcceptIn(In):
    doc_ids: list[int] = Field(min_length=1, max_length=20)


@router.post("/user-docs/accept", status_code=204)
async def accept_user_docs(body: UserDocAcceptIn, request: Request, db: DB, actor: CurrentActor) -> None:
    mine = _my_audiences(actor)
    done = set(await db.scalars(select(UserDocAccept.doc_id).where(UserDocAccept.user_id == actor.id)))
    for d in await db.scalars(select(UserDoc).where(UserDoc.id.in_(body.doc_ids), UserDoc.archived_at.is_(None))):
        if d.audience not in mine or d.id in done:
            continue
        db.add(UserDocAccept(doc_id=d.id, user_id=actor.id, accepted_at=now(), ip=actor.ip,
                             user_agent=(request.headers.get("user-agent") or "")[:255]))
        await write_audit(db, actor_id=actor.id, action="user_doc.accept", entity="user_doc", entity_id=d.id, ip=actor.ip,
                          after={"title": d.title, "audience": d.audience})
    await db.commit()


@router.get("/user-docs/journal")
async def user_docs_journal(db: DB, actor: Actor = require("settings", "view"), doc_id: int | None = None,
                            limit: int = 500) -> list[dict]:
    """Who accepted which file and when (removed files stay in the journal)."""
    q = (select(UserDocAccept, UserDoc, User).join(UserDoc, UserDoc.id == UserDocAccept.doc_id)
         .join(User, User.id == UserDocAccept.user_id).order_by(UserDocAccept.id.desc()).limit(max(1, min(limit, 2000))))
    if doc_id:
        q = q.where(UserDocAccept.doc_id == doc_id)
    names = await _audiences(db)
    return [{"id": a.id, "doc_id": d.id, "title": d.title, "audience": d.audience, "audience_name": names.get(d.audience, d.audience),
             "removed": d.archived_at is not None, "user_id": u.id, "user_name": u.full_name, "accepted_at": a.accepted_at, "ip": a.ip}
            for a, d, u in (await db.execute(q)).all()]


# ---------- complaints ----------
async def owner_ids(db: DB) -> set[int]:
    return set(await db.scalars(select(UserRole.user_id).join(Role, Role.id == UserRole.role_id)
                                .join(User, User.id == UserRole.user_id)
                                .where(Role.code == "owner", User.is_active.is_(True))))

class ComplaintIn(In):
    subject: str = Field(min_length=3, max_length=255)
    body: str = Field(min_length=10, max_length=8000)
    branch_id: int | None = None
    against_user_id: int | None = Field(default=None, ge=1)
    file_url: str | None = Field(default=None, max_length=255)


def _view(c: Complaint, for_author: bool) -> dict:
    d = {"id": c.id, "subject": c.subject, "body": c.body, "status": c.status, "created_at": c.created_at,
         "acknowledged_at": c.acknowledged_at, "due_at": c.due_at, "answer": c.answer, "answered_at": c.answered_at,
         "branch_id": c.branch_id, "file_url": files.signed_url(c.file_url) if c.file_url and not c.file_url.startswith("https://")
         else c.file_url}
    if not for_author:
        d |= {"author_id": c.author_id, "against_user_id": c.against_user_id,
              "overdue": c.status not in ("answered", "closed") and c.due_at < now()}
    return d


async def _author_branches(db: DB, actor: Actor) -> list[int]:
    if actor.is_staff:
        q = select(UserBranch.branch_id).where(UserBranch.user_id == actor.id).order_by(UserBranch.id)
    elif actor.user.kind == UserKind.STUDENT:
        q = select(Student.branch_id).where(Student.user_id == actor.id, Student.archived_at.is_(None))
    else:
        q = (select(Student.branch_id).join(StudentGuardian, StudentGuardian.student_id == Student.id)
             .where(StudentGuardian.user_id == actor.id, Student.archived_at.is_(None)))
    return list(dict.fromkeys(await db.scalars(q)))


def _attachment(value: str | None) -> str | None:
    """QA H-3: an attachment is a file uploaded here (its key) or an https link; never javascript:, data: and the like."""
    if not value:
        return None
    v = value.strip()
    if files.path_of(v):
        return v
    u = urlparse(v)
    if u.scheme == "https" and u.netloc and not any(ch.isspace() for ch in v):
        return v
    raise bad_request("Вложение: загрузите файл или укажите ссылку https://")


def _handlers_filter(actor: Actor):
    """Complaints go to the administration; the person complained about never sees them."""
    allowed = actor.branches_for("complaints", "view")
    conds = [(Complaint.against_user_id.is_(None)) | (Complaint.against_user_id != actor.id)]
    if allowed is not None:
        conds.append(Complaint.branch_id.in_(allowed))
    return conds


@router.post("/complaints", status_code=201)
async def file_complaint(body: ComplaintIn, db: DB, actor: CurrentActor) -> dict:
    await hit(f"complaint:{actor.id}", 5, 3600)
    mine = await _author_branches(db, actor)
    # The branch comes from the author: a complaint can't be dropped into a branch the author has nothing to do with.
    if body.branch_id is not None and body.branch_id not in mine:
        raise forbidden("Жалобу можно подать только в свой филиал")
    branch = body.branch_id or (mine[0] if mine else None)
    if body.against_user_id is not None:
        against = await db.get(User, body.against_user_id)
        if against is None or against.id == actor.id or against.archived_at is not None:
            raise bad_request("Неизвестно, на кого жалоба")
    c = Complaint(author_id=actor.id, branch_id=branch, subject=body.subject, body=body.body,
                  against_user_id=body.against_user_id, file_url=_attachment(body.file_url), status="new",
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
    rows = list(await db.scalars(q.order_by(Complaint.due_at).limit(500)))
    names = dict((await db.execute(select(User.id, User.full_name).where(User.id.in_(
        {c.author_id for c in rows} | {c.against_user_id for c in rows if c.against_user_id})))).all()) if rows else {}
    return [_view(c, False) | {"author_name": names.get(c.author_id), "against_name": names.get(c.against_user_id)}
            for c in rows]


class ComplaintAction(In):
    action: str = Field(pattern="^(acknowledge|investigate|answer|close|appeal)$")
    answer: str | None = Field(default=None, max_length=8000)


@router.post("/complaints/{complaint_id}")
async def act(complaint_id: int, body: ComplaintAction, db: DB, actor: CurrentActor) -> dict:
    ensure_staff_mfa(actor)
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
