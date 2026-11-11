from datetime import date, datetime, time

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import func, select

from app.core.audit import diff, snapshot, write_audit
from app.core.deps import DB, Actor, require
from app.core.errors import bad_request, conflict, forbidden, not_found
from app.core.query import contains_digits, icontains, paginate
from app.core.schemas import Page
from app.core.security import mask_phone, normalize_phone
from app.models import (
    Book,
    BookMovement,
    Freeze,
    Group,
    GroupMember,
    Level,
    Payment,
    Student,
    StudentGuardian,
    SubscriptionPackage,
    Transfer,
    User,
)
from app.models.identity import Role, UserKind, UserRole
from app.models.learning import BalanceEntry, StudentStatus
from app.modules.students.schemas import (
    BalanceOut,
    FreezeIn,
    GuardianIn,
    GuardianOut,
    GuardianPatch,
    LedgerOut,
    StudentIn,
    StudentListOut,
    StudentOut,
    StudentPatch,
    TransferIn,
    TransferPreview,
)
from app.modules.students.scope import get_student_scoped, student_filter
from app.services import balance as bal
from app.modules.auth.service import revoke_all
from app.services import chats
from app.services.realtime import sessions_ended
from app.services.clock import now, today
from app.services.coins import balance as coin_balance
from app.services.values import setting

router = APIRouter(prefix="/students", tags=["students"])


def _age(b: date | None) -> int | None:
    if not b:
        return None
    t = today()
    return t.year - b.year - ((t.month, t.day) < (b.month, b.day))


def _phone(actor: Actor, phone: str | None) -> str | None:
    return phone if actor.can("students", "view_contacts") else mask_phone(phone)


async def _group_names(db: DB, ids: list[int]) -> dict[int, list[str]]:
    out: dict[int, list[str]] = {}
    if not ids:
        return out
    rows = await db.execute(
        select(GroupMember.student_id, Group.name).join(Group, Group.id == GroupMember.group_id)
        .where(GroupMember.student_id.in_(ids), GroupMember.left_on.is_(None))
    )
    for sid, name in rows.all():
        out.setdefault(sid, []).append(name)
    return out


def _list_out(s: Student, actor: Actor, groups: list[str]) -> StudentListOut:
    return StudentListOut(
        id=s.id, full_name=s.full_name, phone=_phone(actor, s.phone), branch_id=s.branch_id, level_id=s.level_id,
        status=s.status, group_names=groups, lessons_left=s.lessons_left, money_balance=s.money_balance,
        last_payment_at=s.last_payment_at, last_visit_at=s.last_visit_at, age=_age(s.birth_date),
    )


async def ensure_role(db: DB, user: User, code: str) -> None:
    role = await db.scalar(select(Role).where(Role.code == code))
    if role and not await db.scalar(select(UserRole).where(UserRole.user_id == user.id, UserRole.role_id == role.id)):
        db.add(UserRole(user_id=user.id, role_id=role.id))


async def upsert_portal_user(db: DB, phone: str, full_name: str, kind: str, locale: str = "ru") -> User:
    """Find the user by phone or create a portal (student/parent) account. Staff phones are never reused."""
    phone = normalize_phone(phone)
    u = await db.scalar(select(User).where(User.phone == phone))
    if u is None:
        u = User(kind=kind, full_name=full_name, phone=phone, locale=locale)
        db.add(u)
        await db.flush()
    elif u.kind == UserKind.STAFF:
        raise conflict("Этот телефон принадлежит сотруднику")
    elif u.kind != kind:
        raise conflict("Этот телефон уже используется другим аккаунтом")
    await ensure_role(db, u, kind)
    return u


async def add_guardian(db: DB, student: Student, g: GuardianIn) -> StudentGuardian:
    u = await upsert_portal_user(db, g.phone, g.full_name, UserKind.PARENT, g.locale)
    link = await db.scalar(select(StudentGuardian).where(StudentGuardian.student_id == student.id, StudentGuardian.user_id == u.id))
    if link is None:
        link = StudentGuardian(student_id=student.id, user_id=u.id, relation=g.relation,
                               whatsapp=normalize_phone(g.whatsapp) if g.whatsapp else None, notify=g.notify)
        db.add(link)
    return link


async def card(db: DB, s: Student, actor: Actor) -> StudentOut:
    gl = (await db.execute(
        select(StudentGuardian, User).join(User, User.id == StudentGuardian.user_id).where(StudentGuardian.student_id == s.id)
    )).all()
    groups = (await db.execute(
        select(GroupMember, Group).join(Group, Group.id == GroupMember.group_id)
        .where(GroupMember.student_id == s.id).order_by(GroupMember.joined_on.desc())
    )).all()
    sub = (await db.execute(
        select(Payment.valid_to, SubscriptionPackage.name).join(SubscriptionPackage, SubscriptionPackage.id == Payment.package_id)
        .where(Payment.student_id == s.id, Payment.valid_to >= today(), Payment.refunded < Payment.amount)
        .order_by(Payment.valid_to.desc()).limit(1)
    )).first()
    return StudentOut(
        **_list_out(s, actor, [g.name for m, g in groups if m.left_on is None]).model_dump(),
        subscription={"name": sub[1], "valid_to": sub[0].isoformat()} if sub else None,
        birth_date=s.birth_date, photo_url=s.photo_url, source=s.source, notes=s.notes, contract_no=s.contract_no, contract_date=s.contract_date,
        sales_user_id=s.sales_user_id, office_user_id=s.office_user_id, user_id=s.user_id, stars=s.stars,
        coins=await coin_balance(db, s.id),
        balance=BalanceOut(lessons_paid=s.lessons_paid, lessons_done=s.lessons_done, lessons_left=s.lessons_left,
                           money_balance=s.money_balance, lesson_price=s.balance_lesson_price),
        guardians=[GuardianOut(id=g.id, user_id=u.id, full_name=u.full_name, phone=_phone(actor, g.whatsapp or u.phone),
                               relation=g.relation, notify=g.notify) for g, u in gl],
        groups=[{"id": g.id, "name": g.name, "joined_on": m.joined_on, "left_on": m.left_on, "level_id": g.level_id,
                 "teacher_id": g.teacher_id} for m, g in groups],
        created_at=s.created_at, archived_at=s.archived_at,
    )


@router.get("", response_model=Page[StudentListOut])
async def list_students(
    db: DB, actor: Actor = require("students", "view"), q: str | None = None, branch_id: int | None = None,
    status: str | None = None, level_id: int | None = None, group_id: int | None = None, debt: bool = False,
    archived: bool = False, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
) -> Page[StudentListOut]:
    stmt = select(Student).where(student_filter(actor))
    stmt = stmt.where(Student.archived_at.is_not(None) if archived else Student.archived_at.is_(None))
    if q:
        digits = "".join(c for c in q if c.isdigit())
        stmt = stmt.where(icontains(Student.full_name, q) | (contains_digits(Student.phone, digits) if len(digits) >= 4 and actor.can("students", "view_contacts") else False))
    if branch_id:
        stmt = stmt.where(Student.branch_id == branch_id)
    if status:
        stmt = stmt.where(Student.status == status)
    if level_id:
        stmt = stmt.where(Student.level_id == level_id)
    if group_id:
        stmt = stmt.where(Student.id.in_(select(GroupMember.student_id).where(GroupMember.group_id == group_id,
                                                                            GroupMember.left_on.is_(None))))
    if debt:
        stmt = stmt.where(Student.lessons_left <= 0, Student.status == StudentStatus.ACTIVE)
    rows, total = await paginate(db, stmt.order_by(Student.full_name), limit, offset)
    names = await _group_names(db, [s.id for s in rows])
    return Page(items=[_list_out(s, actor, names.get(s.id, [])) for s in rows], total=total, limit=limit, offset=offset)


async def _contract_free(db: DB, contract_no: str | None, student_id: int | None = None) -> None:
    if not contract_no:
        return
    q = select(Student.id).where(Student.contract_no == contract_no, Student.archived_at.is_(None))
    if student_id:
        q = q.where(Student.id != student_id)
    if await db.scalar(q):
        raise conflict(f"Договор № {contract_no} уже есть у другого ученика")


@router.post("", response_model=StudentOut, status_code=201)
async def create_student(body: StudentIn, db: DB, actor: Actor = require("students", "create")) -> StudentOut:
    actor.ensure_branch("students", "create", body.branch_id)
    if body.status not in StudentStatus.ALL:
        raise bad_request("Неизвестный статус")
    phone = normalize_phone(body.phone) if body.phone else None
    if phone and await db.scalar(select(Student).where(Student.phone == phone, Student.archived_at.is_(None))):
        raise conflict("Ученик с таким телефоном уже есть")
    contract_no = (body.contract_no or "").strip() or None
    await _contract_free(db, contract_no)
    level = await db.get(Level, body.level_id) if body.level_id else None
    s = Student(full_name=body.full_name, birth_date=body.birth_date, phone=phone, branch_id=body.branch_id,
                contract_no=contract_no, contract_date=body.contract_date,
                level_id=body.level_id, source=body.source, status=body.status, notes=body.notes,
                balance_lesson_price=level.lesson_price if level else 0)
    db.add(s)
    await db.flush()
    if body.create_account and phone:
        u = await upsert_portal_user(db, phone, body.full_name, UserKind.STUDENT)
        s.user_id = u.id
    for g in body.guardians:
        await add_guardian(db, s, g)
    await write_audit(db, actor_id=actor.id, action="student.create", entity="student", entity_id=s.id,
                      branch_id=s.branch_id, ip=actor.ip, after=snapshot(s, ["full_name", "branch_id", "level_id", "status"]))
    await db.commit()
    return await card(db, s, actor)


@router.get("/{student_id}", response_model=StudentOut)
async def get_student(student_id: int, db: DB, actor: Actor = require("students", "view")) -> StudentOut:
    return await card(db, await get_student_scoped(db, actor, student_id), actor)


@router.patch("/{student_id}", response_model=StudentOut)
async def update_student(student_id: int, body: StudentPatch, db: DB, actor: Actor = require("students", "edit")) -> StudentOut:
    s = await get_student_scoped(db, actor, student_id, "students", "edit")
    fields = ["full_name", "birth_date", "phone", "level_id", "source", "notes", "photo_url", "contract_no", "contract_date", "status"]
    before = snapshot(s, fields)
    data = body.model_dump(exclude_unset=True)
    if "status" in data and (data["status"] is None or s.status == "frozen"):
        data.pop("status")  # a freeze is ended through «Снять заморозку»
    if "contract_no" in data:
        data["contract_no"] = (data["contract_no"] or "").strip() or None
        await _contract_free(db, data["contract_no"], s.id)
    if "phone" in data and data["phone"]:
        data["phone"] = normalize_phone(data["phone"])
    if data.get("phone") and data["phone"] != s.phone:
        if await db.scalar(select(Student.id).where(Student.phone == data["phone"], Student.id != s.id,
                                                    Student.archived_at.is_(None))):
            raise conflict("Ученик с таким телефоном уже есть")
        if s.user_id and await db.scalar(select(User.id).where(User.phone == data["phone"], User.id != s.user_id)):
            raise conflict("Этот телефон уже используется другим аккаунтом")
    for k, v in data.items():
        setattr(s, k, v)
    # The student's own account follows the card: the phone is the portal login.
    if s.user_id and (u := await db.get(User, s.user_id)) is not None:
        if data.get("phone") and u.phone != s.phone:
            u.phone = s.phone
        if "full_name" in data and data["full_name"]:
            u.full_name = s.full_name
    b, a = diff(before, snapshot(s, fields))
    await write_audit(db, actor_id=actor.id, action="student.update", entity="student", entity_id=s.id,
                      branch_id=s.branch_id, ip=actor.ip, before=b, after=a)
    await db.commit()
    return await card(db, s, actor)


@router.post("/{student_id}/guardians", response_model=StudentOut)
async def post_guardian(student_id: int, body: GuardianIn, db: DB, actor: Actor = require("students", "edit")) -> StudentOut:
    s = await get_student_scoped(db, actor, student_id, "students", "edit")
    await add_guardian(db, s, body)
    await write_audit(db, actor_id=actor.id, action="student.guardian_add", entity="student", entity_id=s.id,
                      branch_id=s.branch_id, ip=actor.ip, after={"name": body.full_name, "relation": body.relation})
    await db.commit()
    return await card(db, s, actor)


async def _guardian(db: DB, s: Student, guardian_id: int) -> tuple[StudentGuardian, User]:
    link = await db.get(StudentGuardian, guardian_id)
    if link is None or link.student_id != s.id:
        raise not_found("Родитель")
    return link, await db.get(User, link.user_id)


@router.patch("/{student_id}/guardians/{guardian_id}", response_model=StudentOut)
async def edit_guardian(student_id: int, guardian_id: int, body: GuardianPatch, db: DB,
                        actor: Actor = require("students", "edit")) -> StudentOut:
    """Fix a parent's name, phone (= their portal login), relation or WhatsApp notifications. The name and phone
    belong to the parent's account, so a brother or sister of the student sees the same change."""
    s = await get_student_scoped(db, actor, student_id, "students", "edit")
    link, u = await _guardian(db, s, guardian_id)
    data = body.model_dump(exclude_unset=True)
    before = {"name": u.full_name, "phone": u.phone, "relation": link.relation, "notify": link.notify}
    if data.get("phone"):
        if not (actor.can("students", "view_contacts") or actor.is_owner):
            raise forbidden("Телефон меняет сотрудник с доступом к контактам")
        phone = normalize_phone(data["phone"])
        if len(phone) != 12 or not phone.startswith("+7"):
            raise bad_request("Неверный телефон")
        if phone != u.phone:
            if await db.scalar(select(User.id).where(User.phone == phone, User.id != u.id)):
                raise conflict("Этот телефон уже используется другим аккаунтом")
            u.phone = phone
            if link.whatsapp:
                link.whatsapp = phone
    if data.get("full_name"):
        u.full_name = data["full_name"].strip()
    if "relation" in data:
        link.relation = (data["relation"] or "").strip() or None
    if data.get("notify") is not None:
        link.notify = data["notify"]
    after = {"name": u.full_name, "phone": u.phone, "relation": link.relation, "notify": link.notify}
    b, a = diff(before, after)
    if a:
        for k in ("phone",):
            if k in a:
                b[k], a[k] = mask_phone(b[k]) if b.get(k) else None, mask_phone(a[k])
        await write_audit(db, actor_id=actor.id, action="student.guardian_edit", entity="student", entity_id=s.id,
                          branch_id=s.branch_id, ip=actor.ip, before=b, after=a)
    await db.commit()
    return await card(db, s, actor)


@router.delete("/{student_id}/guardians/{guardian_id}", response_model=StudentOut)
async def remove_guardian(student_id: int, guardian_id: int, db: DB, actor: Actor = require("students", "edit")) -> StudentOut:
    """Unlink a parent from this student (the parent's account and other children stay)."""
    s = await get_student_scoped(db, actor, student_id, "students", "edit")
    link, u = await _guardian(db, s, guardian_id)
    await db.delete(link)
    await write_audit(db, actor_id=actor.id, action="student.guardian_remove", entity="student", entity_id=s.id,
                      branch_id=s.branch_id, ip=actor.ip, before={"name": u.full_name, "relation": link.relation})
    await db.commit()
    return await card(db, s, actor)


@router.post("/{student_id}/archive", status_code=204)
async def archive_student(student_id: int, db: DB, actor: Actor = require("students", "archive")) -> None:
    s = await get_student_scoped(db, actor, student_id, "students", "archive")
    s.archived_at = now()
    for m, g in (await db.execute(select(GroupMember, Group).join(Group).where(GroupMember.student_id == s.id,
                                                                               GroupMember.left_on.is_(None)))).all():
        m.left_on = today()
        await chats.sync_student_in_group_chat(db, g, s, False)
    # The student's own account signs out everywhere, open chat sockets included (QA C-5).
    portal = await db.get(User, s.user_id) if s.user_id else None
    if portal is not None and portal.kind == UserKind.STUDENT:
        await revoke_all(db, portal.id, "archived")
    await write_audit(db, actor_id=actor.id, action="student.archive", entity="student", entity_id=s.id,
                      branch_id=s.branch_id, ip=actor.ip)
    await db.commit()
    if portal is not None and portal.kind == UserKind.STUDENT:
        await sessions_ended(portal.id)


@router.get("/{student_id}/ledger", response_model=list[LedgerOut])
async def ledger(student_id: int, db: DB, actor: Actor = require("students", "view")) -> list[LedgerOut]:
    s = await get_student_scoped(db, actor, student_id)
    rows = await db.scalars(select(BalanceEntry).where(BalanceEntry.student_id == s.id).order_by(BalanceEntry.id.desc()).limit(300))
    return [LedgerOut.model_validate(r) for r in rows]


# ---------- history ----------
STATUS_RU = {"lead": "Лид", "trial": "Пробный", "active": "Учится", "frozen": "Заморозка", "finished": "Закончил обучение",
             "left": "Ушёл"}
FIELD_RU = {"full_name": "ФИО", "phone": "Телефон", "birth_date": "Дата рождения", "source": "Откуда узнал",
            "contract_no": "Договор", "contract_date": "Дата договора", "notes": "Заметки"}
SIMPLE_EVENTS = {
    "student.create": ("created", "Добавлен в систему"),
    "student.import": ("created", "Перенесён из старой CRM"),
    "student.left": ("status", "Отмечен как ушедший (нет занятий)"),
    "student.blocked": ("status", "Доступ закрыт: нет оплаты"),
    "student.freeze": ("freeze", "Заморозка"),
    "student.freeze_started": ("freeze", "Заморозка началась"),
    "student.unfreeze": ("freeze", "Заморозка снята"),
    "student.freeze_ended": ("freeze", "Заморозка закончилась"),
    "student.archive": ("status", "Удалён (в архиве)"),
    "student.guardian_add": ("other", "Добавлен родитель"),
    "student.guardian_edit": ("other", "Изменены данные родителя"),
    "student.guardian_remove": ("other", "Родитель убран из карточки"),
    "student.import_balance": ("other", "Перенесён остаток уроков"),
}


class HistoryItem(BaseModel):
    at: datetime
    kind: str  # created | group | transfer | status | level | branch | freeze | other
    text: str
    actor: str | None = None


@router.get("/{student_id}/history", response_model=list[HistoryItem])
async def history(student_id: int, db: DB, actor: Actor = require("students", "view")) -> list[HistoryItem]:
    """Timeline of the student: groups joined/left, transfers, status, level and branch changes, freezes. Built from
    the group memberships and the audit log, so it also covers the time before this page existed."""
    from app.models import AuditLog, Branch
    from app.services.clock import at_local
    s = await get_student_scoped(db, actor, student_id)
    levels = {x.id: x.name for x in await db.scalars(select(Level))}
    branches = {x.id: x.name for x in await db.scalars(select(Branch))}
    out: list[HistoryItem] = []
    for m, g in (await db.execute(select(GroupMember, Group).join(Group, Group.id == GroupMember.group_id)
                                  .where(GroupMember.student_id == s.id))).all():
        lvl = f" ({levels[g.level_id]})" if g.level_id in levels else ""
        out.append(HistoryItem(at=at_local(m.joined_on, time(0)), kind="group", text=f"Начал заниматься в группе «{g.name}»{lvl}"))
        if m.left_on:
            out.append(HistoryItem(at=at_local(m.left_on, time(0)), kind="group", text=f"Вышел из группы «{g.name}»{lvl}"))
        elif g.status == "finished":
            out.append(HistoryItem(at=at_local(g.updated_at.date() if g.updated_at else m.joined_on, time(0)), kind="group",
                                   text=f"Группа «{g.name}» закончила курс{lvl}"))
    logs = (await db.scalars(select(AuditLog).where(AuditLog.entity == "student", AuditLog.entity_id == s.id)
                             .order_by(AuditLog.id).limit(500))).all()
    names = {u.id: u.full_name for u in await db.scalars(
        select(User).where(User.id.in_({x.actor_id for x in logs if x.actor_id} or {0})))}
    for a in logs:
        who = names.get(a.actor_id) if a.actor_id else "Система"
        b, af = a.before or {}, a.after or {}
        if a.action == "student.transfer":
            out.append(HistoryItem(at=a.at, kind="transfer", actor=who,
                                   text=f"Переведён из «{b.get('group') or '—'}» в «{af.get('group')}»"))
        elif a.action == "student.update":
            for k, v in af.items():
                if k == "status":
                    out.append(HistoryItem(at=a.at, kind="status", actor=who,
                                           text=f"Статус: {STATUS_RU.get(b.get(k), b.get(k) or '—')} → {STATUS_RU.get(v, v)}"))
                elif k == "level_id":
                    out.append(HistoryItem(at=a.at, kind="level", actor=who,
                                           text=f"Уровень: {levels.get(b.get(k), '—')} → {levels.get(v, '—')}"))
                elif k == "branch_id":
                    out.append(HistoryItem(at=a.at, kind="branch", actor=who,
                                           text=f"Филиал: {branches.get(b.get(k), '—')} → {branches.get(v, '—')}"))
                elif k in FIELD_RU:
                    out.append(HistoryItem(at=a.at, kind="other", actor=who, text=f"Изменено: {FIELD_RU[k]}"))
        elif a.action in SIMPLE_EVENTS:
            kind, text = SIMPLE_EVENTS[a.action]
            if a.action == "student.freeze" and af.get("from"):
                text = f"Заморозка {date.fromisoformat(af['from']):%d.%m.%Y} – {date.fromisoformat(af['to']):%d.%m.%Y}"
            if a.note:
                text = f"{text}. {a.note}"
            out.append(HistoryItem(at=a.at, kind=kind, actor=who, text=text))
    for e in await db.scalars(select(BalanceEntry).where(BalanceEntry.student_id == s.id, BalanceEntry.kind == "manual",
                                                         BalanceEntry.note.is_not(None))):
        if "старой CRM" in (e.note or ""):
            out.append(HistoryItem(at=e.at, kind="other", text=f"{e.note}: {e.money_delta:+,} ₸".replace(",", " ")))
    out.sort(key=lambda x: x.at, reverse=True)
    return out


# ---------- transfers (ТЗ 5.3) ----------
async def _transfer_ctx(db: DB, s: Student, to_group_id: int):
    to_group = await db.get(Group, to_group_id)
    if to_group is None or to_group.archived_at is not None:
        raise not_found("Группа")
    current = (await db.execute(
        select(GroupMember, Group).join(Group, Group.id == GroupMember.group_id)
        .where(GroupMember.student_id == s.id, GroupMember.left_on.is_(None)).order_by(GroupMember.id.desc())
    )).first()
    if current and current[1].id == to_group.id:
        raise bad_request("Ученик уже в этой группе")
    old_level = await db.get(Level, s.level_id) if s.level_id else None
    new_level = await db.get(Level, to_group.level_id)
    old_price = s.balance_lesson_price or (old_level.lesson_price if old_level else new_level.lesson_price)
    calc = bal.calc_transfer(s.lessons_left, s.money_balance, old_price, new_level.lesson_price)
    return to_group, current, old_level, new_level, calc


@router.post("/{student_id}/transfer/preview", response_model=TransferPreview)
async def transfer_preview(student_id: int, body: TransferIn, db: DB, actor: Actor = require("students", "transfer")) -> TransferPreview:
    s = await get_student_scoped(db, actor, student_id, "students", "transfer")
    to_group, current, old_level, new_level, calc = await _transfer_ctx(db, s, body.to_group_id)
    actor.ensure_branch("students", "transfer", to_group.branch_id)
    hint = None
    if old_level and new_level.id != old_level.id:
        book = await db.scalar(select(Book).where(Book.level_id == new_level.id, Book.archived_at.is_(None)))
        has = book and await db.scalar(select(BookMovement.id).where(BookMovement.student_id == s.id, BookMovement.book_id == book.id))
        if book and not has:
            hint = f"Нужна книга уровня: «{book.title}»"
    return TransferPreview(from_group=current[1].name if current else None, to_group=to_group.name,
                           from_level=old_level.name if old_level else None, to_level=new_level.name,
                           same_price=calc.same_price, lessons_before=calc.lessons_before, money_before=calc.money_before,
                           old_price=calc.old_price, new_price=calc.new_price, value=calc.value,
                           lessons_after=calc.lessons_after, money_after=calc.money_after, book_hint=hint)


@router.post("/{student_id}/transfer", response_model=StudentOut)
async def transfer(student_id: int, body: TransferIn, db: DB, actor: Actor = require("students", "transfer")) -> StudentOut:
    s = await get_student_scoped(db, actor, student_id, "students", "transfer")
    to_group, current, old_level, new_level, calc = await _transfer_ctx(db, s, body.to_group_id)
    actor.ensure_branch("students", "transfer", to_group.branch_id)
    members = await db.scalar(select(func.count()).select_from(GroupMember).where(GroupMember.group_id == to_group.id,
                                                                                    GroupMember.left_on.is_(None)))
    if members >= to_group.capacity:
        raise conflict(f"В группе {to_group.name} нет мест ({members}/{to_group.capacity})")
    t = Transfer(student_id=s.id, at=now(), from_group_id=current[1].id if current else None, to_group_id=to_group.id,
                 from_level_id=s.level_id, to_level_id=new_level.id, lessons_before=calc.lessons_before,
                 money_before=calc.money_before, lessons_after=calc.lessons_after, money_after=calc.money_after,
                 actor_id=actor.id, reason=body.reason)
    db.add(t)
    await db.flush()
    if not calc.same_price:
        await bal.apply(db, s, "transfer", lessons=-calc.lessons_before, money=-calc.money_before, price=calc.old_price,
                        ref=("transfer", t.id), actor_id=actor.id, note=f"Перевод: {calc.value} тг по старой цене")
        await bal.apply(db, s, "transfer", lessons=calc.lessons_after, money=calc.money_after, price=calc.new_price,
                        ref=("transfer", t.id), actor_id=actor.id, note=f"Перевод: {calc.lessons_after} ур. × {calc.new_price}")
    if current:
        current[0].left_on = today()
        await chats.sync_student_in_group_chat(db, current[1], s, False)
    db.add(GroupMember(group_id=to_group.id, student_id=s.id, joined_on=today()))
    await chats.sync_student_in_group_chat(db, to_group, s, True)
    s.level_id = new_level.id
    if to_group.branch_id != s.branch_id:
        s.branch_id = to_group.branch_id
    await write_audit(db, actor_id=actor.id, action="student.transfer", entity="student", entity_id=s.id,
                      branch_id=s.branch_id, ip=actor.ip,
                      before={"group": current[1].name if current else None, "lessons": calc.lessons_before, "money": calc.money_before},
                      after={"group": to_group.name, "lessons": calc.lessons_after, "money": calc.money_after})
    await db.commit()
    return await card(db, s, actor)


# ---------- freezes ----------
def _current_freeze(student_id: int, d: date):
    return select(Freeze).where(Freeze.student_id == student_id, Freeze.starts_on <= d,
                                func.coalesce(Freeze.ended_early_on, Freeze.ends_on) > d)


@router.post("/{student_id}/freeze", response_model=StudentOut)
async def freeze(student_id: int, body: FreezeIn, db: DB, actor: Actor = require("students", "transfer")) -> StudentOut:
    """Rules p.362: by request, at most a month per course, and only with a month prepaid. ends_on is the first day back."""
    s = await get_student_scoped(db, actor, student_id, "students", "transfer", lock=True)
    d = today()
    if body.starts_on < d:
        raise bad_request("Заморозка не может начинаться в прошлом")
    if body.ends_on <= body.starts_on:
        raise bad_request("Дата окончания должна быть позже начала")
    if s.status not in (StudentStatus.ACTIVE,):
        raise bad_request("Заморозить можно только ученика со статусом «учится»")
    max_days = int(await setting(db, "freeze_max_days") or 31)
    if (body.ends_on - body.starts_on).days > max_days:
        raise bad_request(f"Заморозка не дольше {max_days} дней")
    overlap = await db.scalar(select(Freeze.id).where(
        Freeze.student_id == s.id, Freeze.starts_on < body.ends_on,
        func.coalesce(Freeze.ended_early_on, Freeze.ends_on) > body.starts_on,
        func.coalesce(Freeze.ended_early_on, Freeze.ends_on) > Freeze.starts_on))
    if overlap:
        raise conflict("На эти даты уже есть заморозка")
    max_count = int(await setting(db, "freeze_max_per_course") or 1)
    used = await db.scalar(select(func.count()).select_from(Freeze).where(Freeze.student_id == s.id,
                                                                          Freeze.created_at >= s.created_at))
    if used >= max_count and not actor.is_owner:
        raise forbidden(f"Лимит заморозок за курс: {max_count}")
    # «При условии предоплаты за месяц»: a month of lessons must already be paid and waiting on the balance.
    prepaid = int(await setting(db, "freeze_prepaid_lessons") or 0)
    if s.lessons_left < prepaid:
        raise bad_request(f"Заморозка — только при предоплате за месяц: нужно {prepaid} ур. на балансе, сейчас {s.lessons_left}")
    f = Freeze(student_id=s.id, starts_on=body.starts_on, ends_on=body.ends_on, reason=body.reason, created_by=actor.id)
    db.add(f)
    if body.starts_on <= d:
        s.status = StudentStatus.FROZEN
    await write_audit(db, actor_id=actor.id, action="student.freeze", entity="student", entity_id=s.id,
                      branch_id=s.branch_id, ip=actor.ip, after={"from": body.starts_on.isoformat(), "to": body.ends_on.isoformat()})
    await db.commit()
    return await card(db, s, actor)


@router.post("/{student_id}/unfreeze", response_model=StudentOut)
async def unfreeze(student_id: int, db: DB, actor: Actor = require("students", "transfer")) -> StudentOut:
    """Ends the current freeze today, or cancels one that hasn't started. A student still marked «заморожен»
    after the freeze ran out (QA B-5) is always unfrozen."""
    s = await get_student_scoped(db, actor, student_id, "students", "transfer", lock=True)
    d = today()
    f = await db.scalar(select(Freeze).where(Freeze.student_id == s.id, Freeze.ended_early_on.is_(None), Freeze.ends_on > d)
                        .order_by(Freeze.starts_on))
    if f is None and s.status != StudentStatus.FROZEN:
        raise bad_request("Активной заморозки нет")
    if f is not None:
        f.ended_early_on = max(d, f.starts_on)  # a future freeze is cancelled: zero days long
    if s.status == StudentStatus.FROZEN:
        s.status = StudentStatus.ACTIVE
    await write_audit(db, actor_id=actor.id, action="student.unfreeze", entity="student", entity_id=s.id,
                      branch_id=s.branch_id, ip=actor.ip, after={"freeze_id": f.id if f else None})
    await db.commit()
    return await card(db, s, actor)


async def is_frozen_on(db: DB, student_id: int, d: date) -> bool:
    return await db.scalar(_current_freeze(student_id, d).with_only_columns(Freeze.id).limit(1)) is not None


@router.get("/{student_id}/attendance")
async def student_attendance(student_id: int, db: DB, actor: Actor = require("students", "view"), limit: int = Query(60, ge=1, le=300)) -> list[dict]:
    """Attendance history for the card (dots), newest first."""
    from app.models import Attendance, Lesson

    s = await get_student_scoped(db, actor, student_id)
    rows = (await db.execute(
        select(Attendance, Lesson.starts_at, Group.name).join(Lesson, Lesson.id == Attendance.lesson_id)
        .outerjoin(Group, Group.id == Lesson.group_id).where(Attendance.student_id == s.id)
        .order_by(Lesson.starts_at.desc()).limit(min(limit, 300)))).all()
    return [{"lesson_id": a.lesson_id, "at": at, "group": g, "status": a.status, "charged": a.charged, "grade": a.grade,
             "comment": a.comment} for a, at, g in rows]
