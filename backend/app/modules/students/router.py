from datetime import date

from fastapi import APIRouter
from sqlalchemy import func, select

from app.core.audit import diff, snapshot, write_audit
from app.core.deps import DB, Actor, require
from app.core.errors import bad_request, conflict, forbidden, not_found
from app.core.query import paginate
from app.core.schemas import Page
from app.core.security import mask_phone, normalize_phone
from app.models import (
    Book,
    BookMovement,
    Freeze,
    Group,
    GroupMember,
    Level,
    Student,
    StudentGuardian,
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
from app.services import chats
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
    return StudentOut(
        **_list_out(s, actor, [g.name for m, g in groups if m.left_on is None]).model_dump(),
        birth_date=s.birth_date, photo_url=s.photo_url, source=s.source, notes=s.notes,
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
    archived: bool = False, limit: int = 50, offset: int = 0,
) -> Page[StudentListOut]:
    stmt = select(Student).where(student_filter(actor))
    stmt = stmt.where(Student.archived_at.is_not(None) if archived else Student.archived_at.is_(None))
    if q:
        digits = "".join(c for c in q if c.isdigit())
        stmt = stmt.where(Student.full_name.ilike(f"%{q}%") | (Student.phone.contains(digits) if len(digits) >= 4 and actor.can("students", "view_contacts") else False))
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


@router.post("", response_model=StudentOut, status_code=201)
async def create_student(body: StudentIn, db: DB, actor: Actor = require("students", "create")) -> StudentOut:
    actor.ensure_branch("students", "create", body.branch_id)
    if body.status not in StudentStatus.ALL:
        raise bad_request("Неизвестный статус")
    phone = normalize_phone(body.phone) if body.phone else None
    if phone and await db.scalar(select(Student).where(Student.phone == phone, Student.archived_at.is_(None))):
        raise conflict("Ученик с таким телефоном уже есть")
    level = await db.get(Level, body.level_id) if body.level_id else None
    s = Student(full_name=body.full_name, birth_date=body.birth_date, phone=phone, branch_id=body.branch_id,
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
    fields = ["full_name", "birth_date", "phone", "level_id", "source", "notes", "photo_url"]
    before = snapshot(s, fields)
    data = body.model_dump(exclude_unset=True)
    if "phone" in data and data["phone"]:
        data["phone"] = normalize_phone(data["phone"])
    for k, v in data.items():
        setattr(s, k, v)
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


@router.post("/{student_id}/archive", status_code=204)
async def archive_student(student_id: int, db: DB, actor: Actor = require("students", "archive")) -> None:
    s = await get_student_scoped(db, actor, student_id, "students", "archive")
    s.archived_at = now()
    for m, g in (await db.execute(select(GroupMember, Group).join(Group).where(GroupMember.student_id == s.id,
                                                                               GroupMember.left_on.is_(None)))).all():
        m.left_on = today()
        await chats.sync_student_in_group_chat(db, g, s, False)
    await write_audit(db, actor_id=actor.id, action="student.archive", entity="student", entity_id=s.id,
                      branch_id=s.branch_id, ip=actor.ip)
    await db.commit()


@router.get("/{student_id}/ledger", response_model=list[LedgerOut])
async def ledger(student_id: int, db: DB, actor: Actor = require("students", "view")) -> list[LedgerOut]:
    s = await get_student_scoped(db, actor, student_id)
    rows = await db.scalars(select(BalanceEntry).where(BalanceEntry.student_id == s.id).order_by(BalanceEntry.id.desc()).limit(300))
    return [LedgerOut.model_validate(r) for r in rows]


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
@router.post("/{student_id}/freeze", response_model=StudentOut)
async def freeze(student_id: int, body: FreezeIn, db: DB, actor: Actor = require("students", "transfer")) -> StudentOut:
    s = await get_student_scoped(db, actor, student_id, "students", "transfer")
    if body.ends_on <= body.starts_on:
        raise bad_request("Дата окончания должна быть позже начала")
    max_days = int(await setting(db, "freeze_max_days") or 31)
    if (body.ends_on - body.starts_on).days > max_days:
        raise bad_request(f"Заморозка не дольше {max_days} дней")
    max_count = int(await setting(db, "freeze_max_per_course") or 1)
    used = await db.scalar(select(func.count()).select_from(Freeze).where(Freeze.student_id == s.id,
                                                                          Freeze.created_at >= s.created_at))
    if used >= max_count and not actor.is_owner:
        raise forbidden(f"Лимит заморозок за курс: {max_count}")
    f = Freeze(student_id=s.id, starts_on=body.starts_on, ends_on=body.ends_on, reason=body.reason, created_by=actor.id)
    db.add(f)
    if body.starts_on <= today():
        s.status = StudentStatus.FROZEN
    await write_audit(db, actor_id=actor.id, action="student.freeze", entity="student", entity_id=s.id,
                      branch_id=s.branch_id, ip=actor.ip, after={"from": body.starts_on.isoformat(), "to": body.ends_on.isoformat()})
    await db.commit()
    return await card(db, s, actor)


@router.post("/{student_id}/unfreeze", response_model=StudentOut)
async def unfreeze(student_id: int, db: DB, actor: Actor = require("students", "transfer")) -> StudentOut:
    s = await get_student_scoped(db, actor, student_id, "students", "transfer")
    f = await db.scalar(select(Freeze).where(Freeze.student_id == s.id, Freeze.ends_on >= today(),
                                             Freeze.ended_early_on.is_(None)).order_by(Freeze.id.desc()))
    if f is None:
        raise bad_request("Активной заморозки нет")
    f.ended_early_on = today()
    s.status = StudentStatus.ACTIVE
    await write_audit(db, actor_id=actor.id, action="student.unfreeze", entity="student", entity_id=s.id,
                      branch_id=s.branch_id, ip=actor.ip)
    await db.commit()
    return await card(db, s, actor)


async def is_frozen_on(db: DB, student_id: int, d: date) -> bool:
    f = await db.scalar(select(Freeze.id).where(Freeze.student_id == student_id, Freeze.starts_on <= d,
                                                func.coalesce(Freeze.ended_early_on, Freeze.ends_on) > d))
    return f is not None
