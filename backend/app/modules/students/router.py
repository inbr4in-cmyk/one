from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.core.audit import diff, snapshot, write_audit
from app.core.deps import DB, Actor, require
from app.core.errors import bad_request, conflict, forbidden, not_found
from app.core.query import contains_digits, icontains, paginate
from app.core.schemas import In, Page
from app.core.security import mask_phone, normalize_phone
from app.models import (
    Attendance,
    Book,
    BookMovement,
    Freeze,
    Group,
    GroupMember,
    Lesson,
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
    LeaveDecisionIn,
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
from app.services import bookpay, chats, retention
from app.services.realtime import sessions_ended
from app.services.clock import at_local, local, now, today
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
        leave_request=({"at": s.leave_requested_at.isoformat(),
                        "by": await db.scalar(select(User.full_name).where(User.id == s.leave_requested_by))}
                       if s.leave_requested_at else None),
        can_decide_leave=await _can_decide_leave(db, actor), leave_reason=s.leave_reason, return_note=s.return_note,
        book_from_payment=bookpay.capacity(s, src) if (src := await bookpay.source(db, s)) else 0,
    )


async def _can_decide_leave(db: DB, actor: Actor) -> bool:
    """«Ушёл» is the methodist's decision (and the owner's). A school without a methodist role: whoever may delete students."""
    if actor.is_owner or await retention.is_methodist(db, actor.id):
        return True
    return actor.can("students", "archive") and not await retention.has_methodists(db)


def _listed(actor: Actor, q: str | None, branch_id: int | None, status: str | None, level_id: int | None,
            group_id: int | None, debt: bool, archived: bool):
    """The students of the list with its filters: the page and the Excel export show the same people."""
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
    return stmt


@router.get("", response_model=Page[StudentListOut])
async def list_students(
    db: DB, actor: Actor = require("students", "view"), q: str | None = None, branch_id: int | None = None,
    status: str | None = None, level_id: int | None = None, group_id: int | None = None, debt: bool = False,
    archived: bool = False, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
) -> Page[StudentListOut]:
    stmt = _listed(actor, q, branch_id, status, level_id, group_id, debt, archived)
    rows, total = await paginate(db, stmt.order_by(Student.full_name), limit, offset)
    names = await _group_names(db, [s.id for s in rows])
    return Page(items=[_list_out(s, actor, names.get(s.id, [])) for s in rows], total=total, limit=limit, offset=offset)


STATUS_RU = {"lead": "Лид", "trial": "Пробный", "active": "Учится", "waiting": "Ждёт группу", "frozen": "На паузе", "finished": "Закончил", "left": "Ушёл"}
EXPORT_MAX = 20000


@router.get("/export.xlsx")
async def export_students(
    db: DB, actor: Actor = require("students", "archive"), q: str | None = None, branch_id: int | None = None,
    status: str | None = None, level_id: int | None = None, group_id: int | None = None, debt: bool = False,
    archived: bool = False,
):
    """Excel of the list as it is filtered (owner, 27.11.2026). Only the administrator and a branch administrator
    (the people who may archive students); a branch administrator gets his branch only. Every export is in the audit log."""
    from app.models import Branch
    from app.modules.finance.router import _xlsx

    rows = list(await db.scalars(_listed(actor, q, branch_id, status, level_id, group_id, debt, archived)
                                 .order_by(Student.full_name).limit(EXPORT_MAX)))
    ids = [s.id for s in rows]
    groups = await _group_names(db, ids)
    branches = dict((await db.execute(select(Branch.id, Branch.name))).all())
    levels = dict((await db.execute(select(Level.id, Level.name))).all())
    parents: dict[int, list[tuple[str, str | None]]] = {}
    if ids:
        for sid, name, phone in (await db.execute(
                select(StudentGuardian.student_id, User.full_name, User.phone)
                .join(User, User.id == StudentGuardian.user_id).where(StudentGuardian.student_id.in_(ids))
                .order_by(StudentGuardian.id))).all():
            parents.setdefault(sid, []).append((name, phone))
    show = actor.can("students", "view_contacts")
    ph = (lambda v: v or "") if show else (lambda v: mask_phone(v) or "")
    d = lambda v: v.strftime("%d.%m.%Y") if v else ""  # noqa: E731
    out = []
    for s in rows:
        ps = parents.get(s.id, [])
        out.append([s.full_name, ph(s.phone), d(s.birth_date), ", ".join(n for n, _ in ps), ", ".join(ph(p) for _, p in ps if p),
                    branches.get(s.branch_id, ""), levels.get(s.level_id, ""), ", ".join(groups.get(s.id, [])),
                    STATUS_RU.get(s.status, s.status), s.lessons_left, s.money_balance, s.contract_no or "", d(s.contract_date),
                    d(local(s.last_payment_at)) if s.last_payment_at else ""])
    await write_audit(db, actor_id=actor.id, action="student.export", entity="student", entity_id=None, ip=actor.ip,
                      branch_id=branch_id, note=f"{len(out)} учеников", after={"count": len(out), "status": status, "archived": archived})
    await db.commit()
    return _xlsx("Ученики", ["ФИО", "Телефон", "Дата рождения", "Родитель", "Телефон родителя", "Филиал", "Уровень", "Группы",
                             "Статус", "Осталось уроков", "Баланс, ₸", "Договор №", "Дата договора", "Последняя оплата"],
                 out, f"students-{today().isoformat()}.xlsx")


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


LEAVE_BACKDATE_DAYS = 92
TRANSFER_BACKDATE_DAYS = 31


async def _refund_absences(db: DB, s: Student, since: date, actor: Actor, why: str, group_id: int | None = None) -> int:
    """A date entered late: lessons charged for not coming on or after `since` go back to the balance."""
    q = (select(Attendance, Lesson.starts_at).join(Lesson, Lesson.id == Attendance.lesson_id)
         .where(Attendance.student_id == s.id, Attendance.charged.is_(True), Attendance.status.not_in(("present", "late")),
                Lesson.starts_at >= at_local(since, time(0))))
    if group_id is not None:
        q = q.where(Lesson.group_id == group_id)
    rows = (await db.execute(q)).all()
    for a, at in rows:
        await bal.apply(db, s, "lesson", lessons=1, price=s.balance_lesson_price, ref=("attendance", a.lesson_id),
                        actor_id=actor.id, counts_as_done=True, note=f"Возврат урока {local(at):%d.%m}: {why}")
        a.charged = False
    return len(rows)


async def _mark_left(db: DB, s: Student, actor: Actor, reason: str, note: str | None, left_on: date | None,
                     return_on: date | None) -> str:
    """«Ушёл» with its day (may be in the past) and, when the student may come back, a task for the branch admin."""
    d = today()
    if left_on and left_on > d:
        raise bad_request("Дата ухода не может быть в будущем")
    if left_on and left_on < d - timedelta(days=LEAVE_BACKDATE_DAYS):
        raise bad_request(f"Дата ухода не раньше чем {LEAVE_BACKDATE_DAYS} дней назад")
    if return_on and return_on <= (left_on or d):
        raise bad_request("Дата возврата должна быть позже даты ухода")
    returned = 0
    if s.status != StudentStatus.LEFT or left_on:  # a student already «ушёл» may get the real day later
        s.status = StudentStatus.LEFT
        s.left_at = at_local(left_on, time(12)) if left_on and left_on < d else now()
        if left_on and left_on < d:
            returned = await _refund_absences(db, s, left_on, actor, "ушёл")
        await retention.leave_groups(db, s, local(s.left_at).date())
    if return_on:
        import re
        note = re.sub(r"^с \d{2}\.\d{2}\.\d{4}(, )?", "", note or "") or None
        note = f"с {return_on:%d.%m.%Y}" + (f", {note}" if note else "")
    s.leave_reason, s.return_note = reason, note
    s.leave_requested_at = s.leave_requested_by = None
    await retention.close_tasks(db, s.id, "leave")
    if note:
        await retention.close_tasks(db, s.id, "return")
        await retention.follow_up(
            db, s, "return", f"Вернуть ученика: {s.full_name}",
            f"Ученик ушёл {local(s.left_at):%d.%m.%Y}. Причина: {reason}\nКогда может вернуться: {note}\n"
            "Свяжитесь с учеником или родителями и верните его на учёбу.", actor.id,
            who=await retention.branch_admins(db, s.branch_id),
            due_at=at_local(return_on, time(10)) if return_on else now() + timedelta(days=7))
    return (f"Ушёл {local(s.left_at):%d.%m.%Y}. Причина: {reason}" + (f". Возврат: {note}" if note else "")
            + (f". Возвращено уроков: {returned}" if returned else ""))


@router.patch("/{student_id}", response_model=StudentOut)
async def update_student(student_id: int, body: StudentPatch, db: DB, actor: Actor = require("students", "edit")) -> StudentOut:
    s = await get_student_scoped(db, actor, student_id, "students", "edit")
    fields = ["full_name", "birth_date", "phone", "level_id", "source", "notes", "photo_url", "contract_no", "contract_date", "status"]
    before = snapshot(s, fields)
    data = body.model_dump(exclude_unset=True)
    if "status" in data and (data["status"] is None or s.status == "frozen"):
        data.pop("status")  # a freeze is ended through «Снять заморозку»
    reason = (data.pop("leave_reason", None) or "").strip() or None
    return_note = (data.pop("return_note", None) or "").strip() or None
    left_on, return_on = data.pop("left_on", None), data.pop("return_on", None)
    leave_note = None
    if data.get("status") == StudentStatus.LEFT and s.status != StudentStatus.LEFT:
        if await _can_decide_leave(db, actor):
            if not reason:
                raise bad_request("Укажите причину ухода")
            data.pop("status")
            leave_note = await _mark_left(db, s, actor, reason, return_note, left_on, return_on)
        else:
            # Not saved as «ушёл» yet: the methodist talks to the student first and decides.
            data.pop("status")
            if s.leave_requested_at is None:
                s.leave_requested_at, s.leave_requested_by = now(), actor.id
                await retention.follow_up(
                    db, s, "leave", f"Связаться с учеником: {s.full_name} хочет уйти",
                    "Сотрудник отметил, что ученик уходит. Свяжитесь с учеником или родителями, узнайте причину и в карточке "
                    "ученика нажмите «Решение»: ушёл (с причиной) или остаётся."
                    + (f"\nКомментарий сотрудника: {reason}" if reason else ""), actor.id)
                await write_audit(db, actor_id=actor.id, action="student.leave_request", entity="student", entity_id=s.id,
                                  branch_id=s.branch_id, ip=actor.ip, note=reason)
    if data.get("status") == StudentStatus.WAITING and s.status != StudentStatus.WAITING and await _in_group(db, s.id):
        raise bad_request("У ученика есть группа. Статус «Ждёт группу» ставится только ученику без группы")
    if data.get("status") in (StudentStatus.ACTIVE, StudentStatus.FINISHED, StudentStatus.WAITING) and s.status == StudentStatus.LEFT:
        if data["status"] == StudentStatus.ACTIVE and s.left_at:
            await retention.rejoin_groups(db, s, local(s.left_at).date())
        s.left_at = None
        await retention.close_tasks(db, s.id, "return")
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
                      branch_id=s.branch_id, ip=actor.ip, before=b, after=a, note=leave_note)
    await db.commit()
    return await card(db, s, actor)


@router.post("/{student_id}/leave-decision", response_model=StudentOut)
async def leave_decision(student_id: int, body: LeaveDecisionIn, db: DB, actor: Actor = require("students", "view")) -> StudentOut:
    """The methodist's answer after talking to the student: really left (with the reason and, if known, when they
    may come back) or stays. Also used to write the reason for a student who is already «ушёл»."""
    s = await get_student_scoped(db, actor, student_id, lock=True)
    if not await _can_decide_leave(db, actor):
        raise forbidden("Решение об уходе ученика принимает методист")
    reason, note = body.reason.strip(), (body.return_note or "").strip() or None
    if body.left:
        if s.status == StudentStatus.FROZEN:
            raise bad_request("Сначала снимите заморозку")
        text = await _mark_left(db, s, actor, reason, note, body.left_on, body.return_on)
    else:
        if s.status == StudentStatus.LEFT:
            if s.left_at:
                await retention.rejoin_groups(db, s, local(s.left_at).date())
            s.status, s.left_at = StudentStatus.ACTIVE, None
        s.leave_reason = s.return_note = None
        text = f"Остаётся учиться. {reason}"
        s.leave_requested_at = s.leave_requested_by = None
        await retention.close_tasks(db, s.id, "leave")
        await retention.close_tasks(db, s.id, "return")
    await write_audit(db, actor_id=actor.id, action="student.leave_decision", entity="student", entity_id=s.id,
                      branch_id=s.branch_id, ip=actor.ip, after={"left": body.left}, note=text)
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


@router.post("/{student_id}/restore", status_code=204)
async def restore_student(student_id: int, db: DB, actor: Actor = require("students", "archive")) -> None:
    """«Восстановить из архива» (owner, branch admin): the student is back in the lists with the status he had."""
    s = await get_student_scoped(db, actor, student_id, "students", "archive")
    if s.archived_at is None:
        return
    if s.phone and await db.scalar(select(Student.id).where(Student.phone == s.phone, Student.archived_at.is_(None), Student.id != s.id)):
        raise conflict("Ученик с таким телефоном уже есть в списке")
    if s.contract_no and await db.scalar(select(Student.id).where(Student.contract_no == s.contract_no,
                                                                   Student.archived_at.is_(None), Student.id != s.id)):
        raise conflict("Ученик с таким номером договора уже есть в списке")
    s.archived_at = None
    await write_audit(db, actor_id=actor.id, action="student.restore", entity="student", entity_id=s.id,
                      branch_id=s.branch_id, ip=actor.ip)
    await db.commit()


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
    "student.restore": ("status", "Восстановлен из архива"),
    "student.leave_request": ("status", "Отмечено, что ученик хочет уйти: задача методисту"),
    "student.leave_decision": ("status", "Решение методиста"),
    "student.guardian_add": ("other", "Добавлен родитель"),
    "student.guardian_edit": ("other", "Изменены данные родителя"),
    "student.guardian_remove": ("other", "Родитель убран из карточки"),
    "student.import_balance": ("other", "Перенесён остаток уроков"),
}


def _span(a: date, b: date) -> str:
    """«2 мес. 5 дн.» between two dates."""
    days = max((b - a).days, 0)
    months, rest = divmod(days, 30)
    if months and rest:
        return f"{months} мес. {rest} дн."
    return f"{months} мес." if months else f"{rest} дн."


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
        end = m.left_on or ((g.updated_at.date() if g.updated_at else m.joined_on) if g.status == "finished" else None)
        # How long the student studied in the group and how many of its lessons they came to.
        visited = int(await db.scalar(
            select(func.count()).select_from(Attendance).join(Lesson, Lesson.id == Attendance.lesson_id)
            .where(Attendance.student_id == s.id, Lesson.group_id == g.id, Attendance.status.in_(("present", "late")))) or 0)
        studied = f"Занимался {_span(m.joined_on, end or today())}, посетил {visited} ур."
        if m.left_on:
            out.append(HistoryItem(at=at_local(m.left_on, time(0)), kind="group", text=f"Вышел из группы «{g.name}»{lvl}. {studied}"))
        elif g.status == "finished":
            out.append(HistoryItem(at=at_local(end, time(0)), kind="group", text=f"Группа «{g.name}» закончила курс{lvl}. {studied}"))
        else:
            out[-1].text += f". Сейчас в группе: {_span(m.joined_on, today())}, посетил {visited} ур."

    logs = (await db.scalars(select(AuditLog).where(AuditLog.entity == "student", AuditLog.entity_id == s.id)
                             .order_by(AuditLog.id).limit(500))).all()
    names = {u.id: u.full_name for u in await db.scalars(
        select(User).where(User.id.in_({x.actor_id for x in logs if x.actor_id} or {0})))}
    for a in logs:
        who = names.get(a.actor_id) if a.actor_id else "Система"
        b, af = a.before or {}, a.after or {}
        if a.action == "student.transfer":
            out.append(HistoryItem(at=a.at, kind="transfer", actor=who,
                                   text=f"Переведён из «{b.get('group') or '—'}» в «{af.get('group')}»"
                                        + (f". Причина: {a.note}" if a.note else "")))
        elif a.action == "student.branch":
            out.append(HistoryItem(at=a.at, kind="branch", actor=who,
                                   text=f"Филиал: {b.get('branch') or '—'} → {af.get('branch') or '—'}"
                                        + (f". Причина: {a.note}" if a.note else "")))
        elif a.action == "student.update":
            for k, v in af.items():
                if k == "status":
                    out.append(HistoryItem(at=a.at, kind="status", actor=who,
                                           text=f"Статус: {STATUS_RU.get(b.get(k), b.get(k) or '—')} → {STATUS_RU.get(v, v)}"
                                                + (f". {a.note}" if a.note else "")))
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
    if to_group.kind == "club":
        raise bad_request("В открытый урок учеников не переводят")
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
    reason = body.need_reason()
    to_group, current, old_level, new_level, calc = await _transfer_ctx(db, s, body.to_group_id)
    actor.ensure_branch("students", "transfer", to_group.branch_id)
    d = today()
    on = body.on or d
    if on > d:
        raise bad_request("Дата перевода не может быть в будущем")
    if on < d - timedelta(days=TRANSFER_BACKDATE_DAYS):
        raise bad_request(f"Дата перевода не раньше чем {TRANSFER_BACKDATE_DAYS} дней назад")
    if current and on < current[0].joined_on:
        raise bad_request(f"Ученик в группе {current[1].name} с {current[0].joined_on:%d.%m.%Y}: дата перевода не может быть раньше")
    members = await db.scalar(select(func.count()).select_from(GroupMember).where(GroupMember.group_id == to_group.id,
                                                                                    GroupMember.left_on.is_(None)))
    if members >= to_group.capacity:
        raise conflict(f"В группе {to_group.name} нет мест ({members}/{to_group.capacity})")
    t = Transfer(student_id=s.id, at=now() if on == d else at_local(on, time(12)), from_group_id=current[1].id if current else None, to_group_id=to_group.id,
                 from_level_id=s.level_id, to_level_id=new_level.id, lessons_before=calc.lessons_before,
                 money_before=calc.money_before, lessons_after=calc.lessons_after, money_after=calc.money_after,
                 actor_id=actor.id, reason=reason)
    db.add(t)
    await db.flush()
    if not calc.same_price:
        await bal.apply(db, s, "transfer", lessons=-calc.lessons_before, money=-calc.money_before, price=calc.old_price,
                        ref=("transfer", t.id), actor_id=actor.id, note=f"Перевод: {calc.value} тг по старой цене")
        await bal.apply(db, s, "transfer", lessons=calc.lessons_after, money=calc.money_after, price=calc.new_price,
                        ref=("transfer", t.id), actor_id=actor.id, note=f"Перевод: {calc.lessons_after} ур. × {calc.new_price}")
    returned = 0
    if current:
        current[0].left_on = on
        if on < d:  # absences charged in the old group after the real day of the move come back
            returned = await _refund_absences(db, s, on, actor, "перевод", current[1].id)
        await chats.sync_student_in_group_chat(db, current[1], s, False)
    db.add(GroupMember(group_id=to_group.id, student_id=s.id, joined_on=on))
    if s.status == StudentStatus.WAITING:
        s.status = StudentStatus.ACTIVE
    await chats.sync_student_in_group_chat(db, to_group, s, True)
    s.level_id = new_level.id
    if to_group.branch_id != s.branch_id:
        s.branch_id = to_group.branch_id
    await write_audit(db, actor_id=actor.id, action="student.transfer", entity="student", entity_id=s.id,
                      branch_id=s.branch_id, ip=actor.ip,
                      before={"group": current[1].name if current else None, "lessons": calc.lessons_before, "money": calc.money_before},
                      after={"group": to_group.name, "lessons": calc.lessons_after, "money": calc.money_after, "on": on.isoformat()},
                      note=reason + (f". Возвращено уроков: {returned}" if returned else ""))
    await db.commit()
    return await card(db, s, actor)


class BranchMoveIn(In):
    branch_id: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=255)


@router.post("/{student_id}/branch", response_model=StudentOut)
async def move_branch(student_id: int, body: BranchMoveIn, db: DB, actor: Actor = require("students", "transfer")) -> StudentOut:
    """«Перенести» → another branch without a group yet (owner, 21.11.2026). The student leaves the groups of the old
    branch from today and waits for a group in the new one; balance, payments and history stay as they are (past
    payments keep the branch they were taken in). The new branch's staff then put the student into a group."""
    from app.models import Branch

    s = await get_student_scoped(db, actor, student_id, "students", "transfer")
    target = await db.get(Branch, body.branch_id)
    if target is None or target.archived_at is not None:
        raise not_found("Филиал")
    if target.id == s.branch_id:
        raise bad_request("Ученик уже в этом филиале")
    old = await db.get(Branch, s.branch_id)
    closed = await retention.leave_groups(db, s, today() - timedelta(days=1))
    if closed and s.status == StudentStatus.ACTIVE:
        s.status = StudentStatus.WAITING
    s.branch_id = target.id
    await write_audit(db, actor_id=actor.id, action="student.branch", entity="student", entity_id=s.id, branch_id=target.id,
                      ip=actor.ip, before={"branch_id": old.id if old else None, "branch": old.name if old else None},
                      after={"branch_id": target.id, "branch": target.name, "groups_closed": closed}, note=body.reason.strip())
    await db.commit()
    return await card(db, s, actor)


async def _in_group(db, student_id: int) -> bool:
    return await db.scalar(select(GroupMember.id).where(GroupMember.student_id == student_id,
                                                         GroupMember.left_on.is_(None)).limit(1)) is not None


# ---------- freezes ----------
FREEZE_BACKDATE_DAYS = 31


def _current_freeze(student_id: int, d: date):
    return select(Freeze).where(Freeze.student_id == student_id, Freeze.starts_on <= d,
                                func.coalesce(Freeze.ended_early_on, Freeze.ends_on) > d)


@router.post("/{student_id}/freeze", response_model=StudentOut)
async def freeze(student_id: int, body: FreezeIn, db: DB, actor: Actor = require("students", "transfer")) -> StudentOut:
    """By request, at most a month per course. No payment and no group are needed (owner, 18.11.2026). ends_on is
    the first day back."""
    s = await get_student_scoped(db, actor, student_id, "students", "transfer", lock=True)
    d = today()
    if body.starts_on < d - timedelta(days=FREEZE_BACKDATE_DAYS):
        raise bad_request(f"Заморозку можно оформить не раньше чем {FREEZE_BACKDATE_DAYS} дней назад")
    if body.ends_on <= body.starts_on:
        raise bad_request("Дата окончания должна быть позже начала")
    if s.status not in StudentStatus.FREEZABLE:
        raise bad_request("Заморозить нельзя: ученик ушёл, закончил курс или уже заморожен")
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
    # A freeze entered late: lessons already taken from the balance on the frozen days come back.
    late = (await db.execute(
        select(Attendance, Lesson.starts_at).join(Lesson, Lesson.id == Attendance.lesson_id)
        .where(Attendance.student_id == s.id, Attendance.charged.is_(True), Attendance.status.not_in(("present", "late")),
               Lesson.starts_at >= at_local(body.starts_on, time(0)), Lesson.starts_at < at_local(body.ends_on, time(0))))).all()
    f = Freeze(student_id=s.id, starts_on=body.starts_on, ends_on=body.ends_on, reason=body.reason, created_by=actor.id)
    db.add(f)
    if body.starts_on <= d < body.ends_on:
        s.status = StudentStatus.FROZEN
    returned = len(late)
    for a, at in late:
        await bal.apply(db, s, "lesson", lessons=1, price=s.balance_lesson_price, ref=("attendance", a.lesson_id),
                        actor_id=actor.id, counts_as_done=True, note=f"Возврат урока {local(at):%d.%m}: заморозка")
        a.charged = False
    await write_audit(db, actor_id=actor.id, action="student.freeze", entity="student", entity_id=s.id,
                      branch_id=s.branch_id, ip=actor.ip, after={"from": body.starts_on.isoformat(), "to": body.ends_on.isoformat()},
                      note=" ".join(x for x in (body.reason, f"Возвращено уроков: {returned}" if returned else None) if x) or None)
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
        s.status = StudentStatus.ACTIVE if await _in_group(db, s.id) else StudentStatus.WAITING
    await write_audit(db, actor_id=actor.id, action="student.unfreeze", entity="student", entity_id=s.id,
                      branch_id=s.branch_id, ip=actor.ip, after={"freeze_id": f.id if f else None})
    await db.commit()
    return await card(db, s, actor)


async def is_frozen_on(db: DB, student_id: int, d: date) -> bool:
    return await db.scalar(_current_freeze(student_id, d).with_only_columns(Freeze.id).limit(1)) is not None


@router.get("/{student_id}/attendance-month")
async def student_attendance_month(student_id: int, db: DB, month: str = Query(pattern=r"^\d{4}-\d{2}$"),
                                   actor: Actor = require("students", "view")) -> dict:
    """The card's calendar: every mark of the month and the days the student was frozen."""
    from app.models import Attendance, Lesson
    from app.services.clock import at_local, local

    s = await get_student_scoped(db, actor, student_id)
    y, m = int(month[:4]), int(month[5:])
    if not (2000 <= y <= 2100 and 1 <= m <= 12):
        raise bad_request("Месяц")
    start = date(y, m, 1)
    end = date(y + (m == 12), m % 12 + 1, 1)
    rows = (await db.execute(
        select(Attendance, Lesson.starts_at, Group.name).join(Lesson, Lesson.id == Attendance.lesson_id)
        .outerjoin(Group, Group.id == Lesson.group_id)
        .where(Attendance.student_id == s.id, Lesson.starts_at >= at_local(start, time(0)), Lesson.starts_at < at_local(end, time(0)),
               Lesson.status != "cancelled")
        .order_by(Lesson.starts_at))).all()
    frozen: set[str] = set()
    for f in await db.scalars(select(Freeze).where(Freeze.student_id == s.id, Freeze.starts_on < end,
                                                   func.coalesce(Freeze.ended_early_on, Freeze.ends_on) > start)):
        d, last = max(f.starts_on, start), min(f.ended_early_on or f.ends_on, end)
        while d < last:
            frozen.add(d.isoformat())
            d += timedelta(days=1)
    return {"month": month,
            "marks": [{"lesson_id": a.lesson_id, "at": at, "date": local(at).date().isoformat(), "time": f"{local(at):%H:%M}",
                       "group": g, "status": a.status, "charged": a.charged, "grade": a.grade, "comment": a.comment}
                      for a, at, g in rows],
            "frozen": sorted(frozen)}


@router.get("/{student_id}/attendance")
async def student_attendance(student_id: int, db: DB, actor: Actor = require("students", "view"), limit: int = Query(60, ge=1, le=300)) -> list[dict]:
    """Attendance history for the card (dots), newest first."""
    from app.models import Attendance, Lesson

    s = await get_student_scoped(db, actor, student_id)
    rows = (await db.execute(
        select(Attendance, Lesson.starts_at, Group.name).join(Lesson, Lesson.id == Attendance.lesson_id)
        .outerjoin(Group, Group.id == Lesson.group_id).where(Attendance.student_id == s.id, Lesson.status != "cancelled")
        .order_by(Lesson.starts_at.desc()).limit(min(limit, 300)))).all()
    return [{"lesson_id": a.lesson_id, "at": at, "group": g, "status": a.status, "charged": a.charged, "grade": a.grade,
             "comment": a.comment} for a, at, g in rows]
