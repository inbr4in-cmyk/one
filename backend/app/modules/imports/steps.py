"""Applying parsed old-CRM rows to our database, one step per file kind, in dependency order.

Preview and commit run the very same code: a preview is a commit inside a SAVEPOINT that is rolled back at the end,
so what the preview says is exactly what the commit will do. Each source row runs in its own SAVEPOINT: a broken row
becomes «error» with a reason and never half-applies.

Caches keep only ids and plain values, never ORM objects: a rolled-back row savepoint expires the objects it touched.
Nothing here sends messages, accrues bonuses/KPI or changes lesson balances, except the opening balance of a student,
which comes from the old CRM's own figures.
"""

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, time, timedelta
from typing import Any, Awaitable, Callable

from fastapi import HTTPException
from sqlalchemy import func, select

from app.core.deps import Actor
from app.models import (
    Attendance,
    BalanceEntry,
    Book,
    BookMovement,
    BookStock,
    Branch,
    Group,
    GroupMember,
    LeadEvent,
    Lesson,
    Level,
    Payment,
    Role,
    Room,
    ScheduleRule,
    Student,
    User,
    UserBranch,
    UserRole,
)
from app.models.crm import LeadSource
from app.models.identity import UserKind
from app.models.imports import ImportRef
from app.models.learning import LessonStatus, StudentStatus
from app.modules.academics import schedule as sched
from app.modules.crm.service import create_lead
from app.modules.imports.parse import (
    KINDS,
    Parsed,
    compact,
    fingerprint,
    group_key,
    norm,
    person_words,
    short_key,
)
from app.modules.students.router import add_guardian, upsert_portal_user
from app.modules.students.schemas import GuardianIn
from app.services import balance as bal
from app.services import chats
from app.services.clock import at_local, now

SOURCE = "import"

# Old CRM level names (with its typos) → our seeded level codes. Unknown names become new levels in the refs step.
LEVEL_ALIASES = {
    "beginner": "BEG", "elementery": "ELE", "elementary": "ELE", "preintermediate": "PRE", "preinter": "PRE",
    "intermediate": "INT", "intermedit": "INT", "upperintermediate": "UPP", "upper": "UPP", "ielts": "IELTS",
    "ff1": "FF1", "ff2": "FF2", "ff3": "FF3", "ff4": "FF4", "familyandfriends1": "FF1", "familyandfriends2": "FF2",
    "familyandfriends3": "FF3", "familyandfriends4": "FF4", "advaced": "ADVANCE", "advanced": "ADVANCE",
}
STUDENT_STATUS = {"занимается": StudentStatus.ACTIVE, "учится": StudentStatus.ACTIVE, "закончил обучение": StudentStatus.FINISHED,
                  "закончил": StudentStatus.FINISHED, "заморожен": StudentStatus.FROZEN, "ушел": StudentStatus.LEFT,
                  "ушёл": StudentStatus.LEFT, "лид": StudentStatus.LEAD, "пробный": StudentStatus.TRIAL}
GROUP_STATUS = {"в работе": "active", "сбор резервов": "recruiting", "формирующаяся": "recruiting", "набор": "recruiting",
                "завершена": "finished", "закрыта": "finished", "архив": "finished"}
METHODS = {"наличные": "cash", "карта": "card", "банковская карта": "card", "kaspi": "kaspi", "каспи": "kaspi",
           "перевод": "transfer", "безналичный": "transfer", "онлайн": "online"}
DEFAULT_ROOM_CAPACITY = 12
# Groups whose level the old CRM never recorded (no level on the group, its students or its attendance map) are put
# on this level, so their students, schedule and attendance still come over; the owner then sets the real level.
NO_LEVEL_CODE = "NOLEVEL"


class RowError(Exception):
    pass


@dataclass
class RowResult:
    row: int
    status: str  # new | update | skip | error
    label: str
    reason: str | None = None


@dataclass
class StudentInfo:
    id: int
    name: str  # norm
    phone: str | None
    branch_id: int


@dataclass
class GroupInfo:
    id: int
    branch_id: int
    level_id: int
    teacher_id: int
    room_id: int | None
    starts_on: date | None


@dataclass
class Ctx:
    db: Any
    actor: Actor
    today: date
    default_branch_id: int | None
    batch: dict[str, list[Parsed]]
    branches: dict[str, int] = field(default_factory=dict)
    branch_names: dict[int, str] = field(default_factory=dict)
    levels: dict[str, int] = field(default_factory=dict)
    level_codes: dict[str, int] = field(default_factory=dict)
    rooms: dict[tuple[int, str], int] = field(default_factory=dict)
    rooms_by_num: dict[tuple[int, str], list[int]] = field(default_factory=lambda: defaultdict(list))
    teachers: dict[str, int] = field(default_factory=dict)
    teacher_short: dict[str, set[int]] = field(default_factory=lambda: defaultdict(set))
    groups: dict[str, GroupInfo] = field(default_factory=dict)
    students: dict[int, StudentInfo] = field(default_factory=dict)
    hints: dict[str, dict[str, Counter]] = field(default_factory=dict)
    books_paid: dict[str, float] = field(default_factory=dict)
    refs: dict[tuple[str, str], tuple[int, int]] = field(default_factory=dict)  # (kind, ext_key) → (ref id, entity id)
    no_level_id: int | None = None
    pending: list[Callable[[], None]] = field(default_factory=list)
    stats: Counter = field(default_factory=Counter)

    # ----- loading -----
    async def load(self) -> None:
        db = self.db
        self.branches.clear(), self.branch_names.clear(), self.levels.clear(), self.level_codes.clear()
        self.rooms.clear(), self.rooms_by_num.clear(), self.teachers.clear(), self.teacher_short.clear()
        self.groups.clear(), self.students.clear()
        for b in await db.scalars(select(Branch).where(Branch.archived_at.is_(None))):
            self.add_branch(b.id, b.name)
        for lv in await db.scalars(select(Level)):
            self.add_level(lv.id, lv.code, lv.name)
        for r in await db.scalars(select(Room).where(Room.archived_at.is_(None))):
            self.add_room(r.id, r.branch_id, r.name)
        for u in await db.scalars(select(User).where(User.kind == UserKind.STAFF, User.archived_at.is_(None))):
            self.add_teacher(u.id, u.full_name)
        for g in await db.scalars(select(Group).where(Group.archived_at.is_(None))):
            self.groups.setdefault(group_key(g.name), GroupInfo(g.id, g.branch_id, g.level_id, g.teacher_id, g.room_id, g.starts_on))
        for s in await db.scalars(select(Student).where(Student.archived_at.is_(None))):
            self.students[s.id] = StudentInfo(s.id, norm(s.full_name), s.phone, s.branch_id)
        self.refs = {(k, key): (i, e) for i, k, key, e in (await db.execute(
            select(ImportRef.id, ImportRef.kind, ImportRef.ext_key, ImportRef.entity_id))).all()}

    def add_branch(self, bid: int, name: str) -> None:
        self.branches[norm(name)] = bid
        self.branch_names[bid] = name

    def add_level(self, lid: int, code: str, name: str) -> None:
        self.level_codes[code.upper()] = lid
        self.levels.setdefault(compact(code), lid)
        self.levels.setdefault(compact(name), lid)

    def add_room(self, rid: int, branch_id: int, name: str) -> None:
        self.rooms[(branch_id, norm(name))] = rid
        nums = re.findall(r"\d+", name)
        if len(nums) == 1:
            self.rooms_by_num[(branch_id, nums[0])].append(rid)

    def add_teacher(self, uid: int, full_name: str) -> None:
        self.teachers.setdefault(norm(full_name), uid)
        if k := short_key(person_words(full_name)):
            self.teacher_short[k].add(uid)

    # ----- lookups -----
    def branch_id(self, name: str | None) -> int | None:
        return self.branches.get(norm(name)) if name else None

    def level_id(self, name: str | None) -> int | None:
        if not name:
            return None
        c = compact(name)
        code = LEVEL_ALIASES.get(c)
        if code and code in self.level_codes:
            return self.level_codes[code]
        return self.levels.get(c)

    def room_id(self, branch_id: int | None, name: str | None) -> int | None:
        if branch_id is None or not name:
            return None
        if (rid := self.rooms.get((branch_id, norm(name)))) is not None:
            return rid
        nums = re.findall(r"\d+", name)
        if len(nums) == 1 and len(found := self.rooms_by_num.get((branch_id, nums[0]), [])) == 1:
            return found[0]
        return None

    def teacher_id(self, refs: list[str]) -> int | None:
        for ref in refs:
            if (uid := self.teachers.get(norm(ref))) is not None:
                return uid
            k = short_key(person_words(ref))
            if k and len(found := self.teacher_short.get(k, set())) == 1:
                return next(iter(found))
        return None

    def hint(self, key: str, what: str) -> str | None:
        c = self.hints.get(key, {}).get(what)
        return c.most_common(1)[0][0] if c else None

    def students_named(self, words: list[str], branch_id: int | None = None) -> list[StudentInfo]:
        """«Фамилия Имя» (as in the attendance map) or «Фамилия И.» (individual lessons, room schedule)."""
        if not words:
            return []
        out = []
        initial = len(words) >= 2 and words[1].endswith(".")
        for s in self.students.values():
            if branch_id is not None and s.branch_id != branch_id:
                continue
            sw = s.name.split(" ")
            if initial:
                if len(sw) >= 2 and sw[0] == words[0] and sw[1].startswith(words[1].rstrip(".")):
                    out.append(s)
            elif sw[:len(words)] == words or (len(words) == 2 and sw[:2] == [words[1], words[0]]):
                out.append(s)
        return out

    def later(self, fn: Callable[[], None]) -> None:
        """Cache updates that must only happen once the row's savepoint succeeded."""
        self.pending.append(fn)


def build_hints(ctx: Ctx) -> None:
    """Groups in the old CRM have no branch or level column: take them from where the group shows up elsewhere —
    the room schedule and attendance map (branch, teacher, level) and the students' rows (branch, level)."""
    h: dict[str, dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
    for p in ctx.batch.get("schedule", []):
        for r in p.rows:
            if re.search(r"\d", r["who"] or ""):
                k = group_key(r["who"])
                h[k]["branch"][r["branch"]] += 3
                if r["teacher"]:
                    h[k]["teacher"][r["teacher"]] += 1
    for p in ctx.batch.get("attendance", []):
        for r in p.rows:
            if re.search(r"\d", r["block"]):
                k = group_key(r["block"])
                if r["branch"]:
                    h[k]["branch"][r["branch"]] += 3
                if r["level"]:
                    h[k]["level"][r["level"]] += 3
                for t in r["teachers"][:1]:
                    h[k]["teacher"][t] += 1
    for p in ctx.batch.get("students", []):
        for r in p.rows:
            for k in r["groups"]:
                if r["branch"]:
                    h[k]["branch"][r["branch"]] += 1
                if r["level"]:
                    h[k]["level"][r["level"]] += 1
    ctx.hints = {k: dict(v) for k, v in h.items()}
    books: dict[str, float] = defaultdict(float)
    for p in ctx.batch.get("payments", []):
        for r in p.rows:
            if _paid(r) and _is_books(r) and r["client_id"]:
                books[r["client_id"]] += r["amount_exact"] if r["amount_exact"] is not None else (r["amount"] or 0)
    ctx.books_paid = dict(books)


# ---------- import refs ----------
async def ref_get(ctx: Ctx, kind: str, key: str) -> ImportRef | None:
    """Looked up in the per-file id map first: a first import of 4 000 payments then costs no query per row."""
    found = ctx.refs.get((kind, key[:255]))
    if found is None:
        return None
    ref = await ctx.db.get(ImportRef, found[0])
    if ref is None:  # created in a row savepoint that was rolled back
        ctx.refs.pop((kind, key[:255]), None)
    return ref


def ref_entity(ctx: Ctx, kind: str, key: str) -> int | None:
    found = ctx.refs.get((kind, key[:255]))
    return found[1] if found else None


async def ref_put(ctx: Ctx, kind: str, key: str, entity: str, entity_id: int, fp: str | None = None, meta: dict | None = None,
                  ref: ImportRef | None = None) -> ImportRef:
    ref = ref or await ref_get(ctx, kind, key)
    if ref is None:
        ref = ImportRef(kind=kind, ext_key=key[:255], entity=entity, entity_id=entity_id, fingerprint=fp, meta=meta or {})
        ctx.db.add(ref)
        await ctx.db.flush()
        ctx.refs[(kind, key[:255])] = (ref.id, entity_id)
    else:
        ctx.refs[(kind, key[:255])] = (ref.id, entity_id)
        ref.entity, ref.entity_id, ref.fingerprint = entity, entity_id, fp
        if meta is not None:
            ref.meta = meta
    await ctx.db.flush()
    return ref


# ---------- shared helpers ----------
def _paid(r: dict) -> bool:
    return norm(r["state"]) in ("оплачен", "оплачено", "проведен")


def _is_books(r: dict) -> bool:
    return "материал" in norm(r["purpose"]) or "книг" in norm(r["purpose"])


async def ensure_rule(ctx: Ctx, group_id: int, weekdays: list[int], start: time | None, end: time | None, room_id: int | None,
                      since: date | None) -> tuple[str, str | None]:
    """A weekly schedule rule for the group, once; lessons are generated from today for the usual horizon.
    → ("new" | "skip", note)."""
    if not weekdays or start is None or end is None or end <= start:
        return "skip", "нет расписания"
    if room_id is None:
        return "skip", "расписание не перенесено: аудитория не найдена"
    db = ctx.db
    existing = await db.scalar(select(ScheduleRule).where(
        ScheduleRule.group_id == group_id, ScheduleRule.archived_at.is_(None), ScheduleRule.start_time == start,
        ScheduleRule.weekdays == sorted(weekdays)))
    if existing is not None:
        return "skip", "расписание уже есть"
    g = await db.get(Group, group_id)
    rule = ScheduleRule(group_id=g.id, weekdays=sorted(weekdays), start_time=start, end_time=end, room_id=room_id,
                        teacher_id=g.teacher_id, valid_from=min(since or ctx.today, ctx.today))
    db.add(rule)
    await db.flush()
    created, problems = await sched.generate(db, rule, g)
    ctx.stats["lessons_planned"] += created
    ctx.stats["rules"] += 1
    note = f"расписание {_days(weekdays)} {start:%H:%M}–{end:%H:%M}, занятий: {created}"
    if problems:
        note += f"; пересечения: {len(problems)} ({problems[0]})"
    return "new", note


def _days(wd: list[int]) -> str:
    names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    return "/".join(names[d] for d in wd)


async def add_member(ctx: Ctx, gi: GroupInfo, student_id: int, joined: date) -> bool:
    db = ctx.db
    if await db.scalar(select(GroupMember.id).where(GroupMember.group_id == gi.id, GroupMember.student_id == student_id,
                                                    GroupMember.left_on.is_(None))):
        return False
    db.add(GroupMember(group_id=gi.id, student_id=student_id, joined_on=joined))
    g = await db.get(Group, gi.id)
    cnt = await db.scalar(select(func.count()).select_from(GroupMember).where(GroupMember.group_id == g.id,
                                                                                GroupMember.left_on.is_(None)))
    if cnt > g.capacity:
        g.capacity = cnt  # the old CRM had no limit; keep the real size instead of dropping students
    s = await db.get(Student, student_id)
    await chats.sync_student_in_group_chat(db, g, s, True)
    ctx.stats["memberships"] += 1
    return True


def _note_join(*parts: str | None) -> str | None:
    text = "\n".join(p for p in parts if p)
    return text[:4000] or None


# ---------- step: reference data (branches, levels, rooms) ----------
async def step_refs(ctx: Ctx) -> list[RowResult]:
    db = ctx.db
    out: list[RowResult] = []
    branch_names: dict[str, str] = {}
    level_names: dict[str, str] = {}
    rooms: dict[tuple[str, str], str] = {}

    def add_branch(name: str | None):
        if name and name not in ("[Нет]", "---"):
            branch_names.setdefault(norm(name), name.strip())

    def add_level(name: str | None):
        if name and name not in ("[Нет]", "---"):
            level_names.setdefault(compact(name), name.strip())

    for p in ctx.batch.get("teachers", []):
        for r in p.rows:
            for b in r["branches"]:
                add_branch(b)
            for lv in r["levels"]:
                add_level(lv)
    for p in ctx.batch.get("students", []):
        for r in p.rows:
            add_branch(r["branch"])
            add_level(r["level"])
    for p in ctx.batch.get("payments", []):
        for r in p.rows:
            add_branch(r["branch"])
    for p in ctx.batch.get("attendance", []):
        for r in p.rows:
            add_branch(r["branch"])
            add_level(r["level"])
    for p in ctx.batch.get("individual", []):
        for r in p.rows:
            add_branch(r["branch"])
            add_level(r["level"])
            if r["room"] and r["branch"]:
                rooms.setdefault((norm(r["branch"]), norm(r["room"])), r["room"])
    for p in ctx.batch.get("schedule", []):
        for r in p.rows:
            add_branch(r["branch"])
            if r["room"] and r["branch"]:
                rooms.setdefault((norm(r["branch"]), norm(r["room"])), r["room"])
    for p in ctx.batch.get("groups", []):
        for r in p.rows:
            b = ctx.hint(r["key"], "branch")
            if r["room"] and b:
                rooms.setdefault((norm(b), norm(r["room"])), r["room"])
            add_level(ctx.hint(r["key"], "level"))

    for key, name in sorted(branch_names.items()):
        bid = ctx.branches.get(key)
        if bid is not None:
            out.append(RowResult(0, "skip", f"Филиал «{name}»", f"уже есть: «{ctx.branch_names[bid]}»"))
            continue
        b = Branch(name=name[:120])
        db.add(b)
        await db.flush()
        ctx.add_branch(b.id, b.name)
        out.append(RowResult(0, "new", f"Филиал «{name}»", "адрес и телефон заполните в настройках"))
    next_order = (await db.scalar(select(func.max(Level.order)))) or 0
    for key, name in sorted(level_names.items()):
        lid = ctx.level_id(name)
        if lid is not None:
            lv = await db.get(Level, lid)
            out.append(RowResult(0, "skip", f"Уровень «{name}»", f"совпадает с «{lv.name}»"))
            continue
        code = (LEVEL_ALIASES.get(key) or re.sub(r"[^A-Z0-9]", "", name.upper()) or f"LVL{next_order + 1}")[:32]
        if code in ctx.level_codes:
            code = f"{code[:28]}{next_order + 1}"
        next_order += 1
        lv = Level(name=name[:80], code=code, track="adults", lesson_price=0, order=next_order, duration_months=3)
        db.add(lv)
        await db.flush()
        ctx.add_level(lv.id, lv.code, lv.name)
        out.append(RowResult(0, "new", f"Уровень «{name}»", "цена урока 0 — укажите её в настройках"))
    no_level = sorted({r["name"] for p in ctx.batch.get("groups", []) for r in p.rows
                       if r["teachers"] and ctx.level_id(ctx.hint(r["key"], "level")) is None})
    if no_level and NO_LEVEL_CODE not in ctx.level_codes:
        next_order += 1
        lv = Level(name="Без уровня", code=NO_LEVEL_CODE, track="adults", lesson_price=0, order=next_order, duration_months=3)
        db.add(lv)
        await db.flush()
        ctx.add_level(lv.id, lv.code, lv.name)
        out.append(RowResult(0, "new", "Уровень «Без уровня»", f"для групп без уровня в старой CRM ({len(no_level)}): "
                             + ", ".join(no_level[:10]) + " — поставьте им настоящий уровень"))
    for (bkey, rkey), name in sorted(rooms.items()):
        bid = ctx.branches.get(bkey)
        if bid is None:
            continue
        rid = ctx.room_id(bid, name)
        label = f"Аудитория «{name}», {ctx.branch_names[bid]}"
        if rid is not None:
            room = await db.get(Room, rid)
            out.append(RowResult(0, "skip", label, f"совпадает с «{room.name}»"))
            continue
        room = Room(branch_id=bid, name=name[:64], capacity=DEFAULT_ROOM_CAPACITY)
        db.add(room)
        await db.flush()
        ctx.add_room(room.id, bid, room.name)
        out.append(RowResult(0, "new", label, f"вместимость {DEFAULT_ROOM_CAPACITY} — проверьте"))
    return out


# ---------- step: teachers ----------
async def step_teacher(ctx: Ctx, r: dict) -> RowResult:
    db = ctx.db
    label = r["full_name"]
    key = norm(r["full_name"])
    fp = fingerprint(r)
    ref = await ref_get(ctx, "teacher", key)
    branch_ids = [b for b in (ctx.branch_id(x) for x in r["branches"]) if b is not None]
    uid = ref.entity_id if ref else ctx.teachers.get(key)
    if uid is not None:
        if ref and ref.fingerprint == fp:
            return RowResult(r["row"], "skip", label, "без изменений")
        u = await db.get(User, uid)
        if u is None or u.kind != UserKind.STAFF:
            raise RowError("сотрудник с этим именем не найден")
        have = set((await db.scalars(select(UserBranch.branch_id).where(UserBranch.user_id == uid))).all())
        for b in set(branch_ids) - have:
            db.add(UserBranch(user_id=uid, branch_id=b))
        await ref_put(ctx, "teacher", key, "user", uid, fp, ref=ref)
        return RowResult(r["row"], "update", label, "найден по ФИО" + (", добавлены филиалы" if set(branch_ids) - have else ""))
    # No phone in the export and never a default password: the account exists for groups and the schedule,
    # and stays closed for sign-in until the owner sets a phone and a password.
    u = User(kind=UserKind.STAFF, full_name=r["full_name"][:255], phone=None, password_hash=None, position="Преподаватель")
    db.add(u)
    await db.flush()
    role = await db.scalar(select(Role).where(Role.code == "teacher"))
    if role:
        db.add(UserRole(user_id=u.id, role_id=role.id))
    for b in set(branch_ids):
        db.add(UserBranch(user_id=u.id, branch_id=b))
    await ref_put(ctx, "teacher", key, "user", u.id, fp)
    new_id, new_name = u.id, u.full_name
    ctx.later(lambda: ctx.add_teacher(new_id, new_name))
    ctx.stats["staff_created"] += 1
    return RowResult(r["row"], "new", label, "без телефона и пароля — вход закрыт, пока владелец не задаст их")


# ---------- step: groups ----------
async def step_group(ctx: Ctx, r: dict) -> RowResult:
    db = ctx.db
    key = r["key"]
    label = f"Группа {r['name']}"
    fp = fingerprint(r)
    ref = await ref_get(ctx, "group", key)
    gi = ctx.groups.get(key)
    if ref and ref.fingerprint == fp:
        return RowResult(r["row"], "skip", label, "без изменений")
    teacher_id = ctx.teacher_id(r["teachers"]) or ctx.teacher_id([t for t in [ctx.hint(key, "teacher")] if t])
    status = GROUP_STATUS.get(norm(r["status"]), "active")
    if r["closed"] and r["closed"] < ctx.today:
        status = "finished"
    if gi is not None:
        g = await db.get(Group, gi.id)
        notes = []
        if ref is None and not r["teachers"] and status != "active":
            await ref_put(ctx, "group", key, "group", g.id, fp)
            return RowResult(r["row"], "skip", label, "группа уже есть")
        if teacher_id and g.teacher_id != teacher_id:
            old = g.teacher_id
            g.teacher_id = teacher_id
            await chats.change_group_teacher(db, g, old)
            notes.append("сменился преподаватель")
        if status == "active" and g.status != "active" or status == "finished" and g.status != "finished":
            g.status = status
            notes.append("статус")
        room_id = ctx.room_id(g.branch_id, r["room"])
        if room_id and g.room_id != room_id:
            g.room_id = room_id
        rs, rnote = await ensure_rule(ctx, g.id, r["weekdays"], r["start"], r["end"], room_id or g.room_id, r["opened"])
        if rs == "new":
            notes.append(rnote)
        await ref_put(ctx, "group", key, "group", g.id, fp, ref=ref)
        gi2 = GroupInfo(g.id, g.branch_id, g.level_id, g.teacher_id, g.room_id, g.starts_on)
        ctx.later(lambda: ctx.groups.__setitem__(key, gi2))
        return RowResult(r["row"], "update" if notes else "skip", label, ", ".join(notes) or "без изменений")
    branch_name = ctx.hint(key, "branch")
    branch_id = ctx.branch_id(branch_name) or ctx.default_branch_id
    level_id = ctx.level_id(ctx.hint(key, "level"))
    level_note = None
    if level_id is None and (level_id := ctx.level_codes.get(NO_LEVEL_CODE)) is not None:
        level_note = "уровень не указан в старой CRM — поставлен «Без уровня»"
    if teacher_id is None:
        who = (r["teachers"] or [ctx.hint(key, "teacher")])[0]
        raise RowError(f"преподаватель «{who}» не найден среди сотрудников" if who else "нет преподавателя — группа не создана")
    if branch_id is None:
        raise RowError("филиал группы не определён: её нет ни в расписании, ни в посещаемости, ни у учеников — "
                       "выберите филиал по умолчанию")
    if level_id is None:
        raise RowError("уровень группы не определён: нет ни в посещаемости, ни у учеников")
    room_id = ctx.room_id(branch_id, r["room"])
    g = Group(name=r["name"][:120], branch_id=branch_id, level_id=level_id, teacher_id=teacher_id, room_id=room_id, capacity=12,
              starts_on=r["opened"], status=status)
    db.add(g)
    await db.flush()
    if not await db.scalar(select(UserBranch.id).where(UserBranch.user_id == teacher_id, UserBranch.branch_id == branch_id)):
        db.add(UserBranch(user_id=teacher_id, branch_id=branch_id))
    await chats.ensure_group_chat(db, g)
    _, rnote = await ensure_rule(ctx, g.id, r["weekdays"], r["start"], r["end"], room_id, r["opened"])
    await ref_put(ctx, "group", key, "group", g.id, fp)
    gi2 = GroupInfo(g.id, g.branch_id, g.level_id, g.teacher_id, g.room_id, g.starts_on)
    ctx.later(lambda: ctx.groups.__setitem__(key, gi2))
    ctx.stats["groups_created"] += 1
    return RowResult(r["row"], "new", label, "; ".join(x for x in (ctx.branch_names.get(branch_id), level_note, rnote) if x))


# ---------- step: students ----------
def _opening_money(ctx: Ctx, r: dict) -> int:
    """Personal account in the old CRM = «Приход» − «Расход». Book purchases are credited to «Приход» there but never
    written off to «Расход», so the paid «Учебные материалы» of the same client are taken out: what is left is the
    money for lessons."""
    inc = float(r["income"] or 0) if isinstance(r["income"], (int, float)) else float(str(r["income"] or 0).replace(",", "."))
    exp = float(r["expense"] or 0) if isinstance(r["expense"], (int, float)) else float(str(r["expense"] or 0).replace(",", "."))
    books = ctx.books_paid.get(r["client_id"] or "", 0.0)
    x = inc - exp - books
    return int(x + 0.5) if x >= 0 else -int(-x + 0.5)


async def step_student(ctx: Ctx, r: dict) -> RowResult:
    db = ctx.db
    name = r["full_name"]
    if not name or len(name) < 2:
        raise RowError("пустое ФИО")
    label = name
    key = r["client_id"] or f"{norm(name)}|{r['phone'] or ''}"
    fp = fingerprint(r)
    ref = await ref_get(ctx, "student", key)
    if ref and ref.fingerprint == fp:
        return RowResult(r["row"], "skip", label, "без изменений")
    branch_id = ctx.branch_id(r["branch"]) or ctx.default_branch_id
    if branch_id is None:
        raise RowError("нет филиала — выберите филиал по умолчанию")
    level_id = ctx.level_id(r["level"])
    status = STUDENT_STATUS.get(norm(r["status"]), StudentStatus.ACTIVE)
    active = status == StudentStatus.ACTIVE
    money_left = _opening_money(ctx, r)
    notes: list[str] = []
    sid: int | None = ref.entity_id if ref else None
    matched = False
    if sid is None:
        nm = norm(name)
        cands = [s for s in ctx.students.values() if s.name == nm and (s.phone == r["phone"] if r["phone"] else s.phone is None)
                 and (r["phone"] or s.branch_id == branch_id)]
        if len(cands) == 1:
            sid, matched = cands[0].id, True
    if sid is not None:
        s = await db.get(Student, sid)
        if s is None:
            raise RowError("ученик из прошлого импорта не найден")
        s.full_name, s.status = name[:255], status
        s.birth_date = r["birth_date"] or s.birth_date
        s.level_id = level_id or s.level_id
        if r["phone"] and not s.phone:
            s.phone = r["phone"]
        prev = (ref.meta or {}).get("money") if ref else None
        if prev is not None and prev != money_left:
            await bal.apply(db, s, "manual", money=money_left - prev, actor_id=ctx.actor.id,
                            note="Изменение остатка в старой CRM (повторный импорт)")
            notes.append(f"остаток {prev} → {money_left} ₸")
        elif prev is None and money_left and not await db.scalar(select(BalanceEntry.id).where(BalanceEntry.student_id == s.id).limit(1)):
            await bal.apply(db, s, "manual", money=money_left, actor_id=ctx.actor.id, note="Остаток на личном счёте в старой CRM")
            notes.append(f"остаток {money_left} ₸")
        notes.insert(0, "найден по ФИО и телефону" if matched else "обновлён")
        result = "update"
    else:
        extra = [f"Перенесён из старой CRM: ИД клиента {r['client_id']}" + (f", ИД {r['crm_id']}" if r["crm_id"] else "")]
        if r["note"]:
            extra.append(r["note"])
        if r["other_groups"]:
            extra.append("Занятия в старой CRM: " + ", ".join(r["other_groups"]))
        if r["bad_phone"]:
            extra.append(f"Телефон в старой CRM: {r['bad_phone']}")
        if not active:
            extra += [f"Контакт: {c['relation'] or 'родитель'} {c['phone']}" for c in r["contacts"]]
        s = Student(full_name=name[:255], phone=r["phone"], birth_date=r["birth_date"], branch_id=branch_id, level_id=level_id,
                    status=status, source=SOURCE, notes=_note_join(*extra))
        db.add(s)
        await db.flush()
        sid = s.id
        if money_left:
            await bal.apply(db, s, "manual", money=money_left, actor_id=ctx.actor.id, note="Остаток на личном счёте в старой CRM")
            notes.append(f"остаток {money_left} ₸")
        result = "new"
        ctx.stats["students_created"] += 1
    # Portal accounts only for students who study now: guardians (parents) and the student's own phone.
    if active:
        for c in r["contacts"]:
            if c["phone"] == r["phone"]:
                continue
            try:
                async with db.begin_nested():
                    await add_guardian(db, s, GuardianIn(full_name=("Родитель — " + name)[:255], phone=c["phone"],
                                                         relation=(c["relation"] or None)))
                    ctx.stats["guardians"] += 1
            except HTTPException as e:
                notes.append(f"родитель не добавлен: {e.detail}")
        if r["phone"] and not s.user_id:
            try:
                async with db.begin_nested():
                    u = await upsert_portal_user(db, r["phone"], name, UserKind.STUDENT)
                    taken = await db.scalar(select(Student.id).where(Student.user_id == u.id, Student.id != s.id).limit(1))
                    if taken:
                        notes.append("телефон уже у другого ученика — кабинет не создан")
                    else:
                        s.user_id = u.id
            except HTTPException as e:
                notes.append(f"кабинет ученика не создан: {e.detail}")
        for gk, gname in zip(r["groups"], r["group_names"]):
            gi = ctx.groups.get(gk)
            if gi is None:
                notes.append(f"группа {gname} не найдена")
                continue
            joined = min(gi.starts_on or ctx.today, ctx.today)
            if await add_member(ctx, gi, s.id, joined):
                notes.append(f"в группе {gname}")
    elif r["groups"]:
        notes.append("закончил обучение — в группы не добавлен")
    await ref_put(ctx, "student", key, "student", s.id, fp, meta={"money": money_left})
    info = StudentInfo(s.id, norm(s.full_name), s.phone, s.branch_id)
    ctx.later(lambda: ctx.students.__setitem__(info.id, info))
    return RowResult(r["row"], result, label, "; ".join(notes) or None)


# ---------- step: individual lessons ----------
async def _individual_group(ctx: Ctx, student_id: int) -> GroupInfo | None:
    ref = await ref_get(ctx, "indgroup", str(student_id))
    if ref is None:
        return None
    g = await ctx.db.get(Group, ref.entity_id)
    return GroupInfo(g.id, g.branch_id, g.level_id, g.teacher_id, g.room_id, g.starts_on) if g else None


def _one_student(ctx: Ctx, words: list[str], branch_id: int | None) -> StudentInfo:
    found = ctx.students_named(words, branch_id)
    if not found and branch_id is not None:
        found = ctx.students_named(words)
    if len(found) > 1:
        active = [s for s in found if s.id in ctx.students]  # all are; keep the message honest
        raise RowError(f"несколько учеников с именем «{' '.join(words)}» ({len(active)}) — уточните вручную")
    if not found:
        raise RowError(f"ученик «{' '.join(words)}» не найден — импортируйте сначала файл учеников")
    return found[0]


async def step_individual(ctx: Ctx, r: dict) -> RowResult:
    db = ctx.db
    label = f"Индивидуально: {r['short_name']}"
    key = r["ext_id"] or f"{norm(r['short_name'])}|{norm(r['branch'])}"
    fp = fingerprint(r)
    ref = await ref_get(ctx, "individual", key)
    if ref and ref.fingerprint == fp:
        return RowResult(r["row"], "skip", label, "без изменений")
    branch_id = ctx.branch_id(r["branch"]) or ctx.default_branch_id
    st = _one_student(ctx, person_words(r["short_name"]), branch_id)
    s = await db.get(Student, st.id)
    branch_id = branch_id or s.branch_id
    teacher_id = ctx.teacher_id(r["teachers"])
    room_id = ctx.room_id(branch_id, r["room"])
    gi = await _individual_group(ctx, s.id)
    notes = []
    if gi is None:
        if teacher_id is None:
            raise RowError(f"преподаватель «{(r['teachers'] or ['—'])[0]}» не найден")
        level_id = ctx.level_id(r["level"]) or s.level_id
        if level_id is None:
            raise RowError("не указан уровень")
        status = "finished" if r["end"] and r["end"] < ctx.today else "active"
        g = Group(name=f"Инд. {s.full_name}"[:120], branch_id=branch_id, level_id=level_id, teacher_id=teacher_id, room_id=room_id,
                  capacity=1, starts_on=r["start"], status=status)
        db.add(g)
        await db.flush()
        if not await db.scalar(select(UserBranch.id).where(UserBranch.user_id == teacher_id, UserBranch.branch_id == branch_id)):
            db.add(UserBranch(user_id=teacher_id, branch_id=branch_id))
        await chats.ensure_group_chat(db, g)
        gi = GroupInfo(g.id, g.branch_id, g.level_id, g.teacher_id, g.room_id, g.starts_on)
        await ref_put(ctx, "indgroup", str(s.id), "group", g.id)
        if status == "active":
            await add_member(ctx, gi, s.id, min(r["start"] or ctx.today, ctx.today))
        if r["debt"]:
            s.notes = _note_join(s.notes, f"Индивидуальные занятия в старой CRM: «Долг, часы» = {r['debt']}")
        result = "new"
        ctx.stats["individual_groups"] += 1
    else:
        result = "update"
        notes.append("занятия уже есть")
    for e in r["schedule"]:
        rs, rnote = await ensure_rule(ctx, gi.id, e["weekdays"], e["start"], e["end"], room_id, e["since"] or r["start"])
        if rs == "new" or result == "new":
            notes.append(rnote)
    if r["cut"]:
        notes.append("в выгрузке не всё расписание — остальное берётся из расписания аудиторий")
    await ref_put(ctx, "individual", key, "group", gi.id, fp, ref=ref)
    return RowResult(r["row"], result, label, "; ".join(n for n in notes if n) or None)


# ---------- step: room schedule ----------
async def _group_for(ctx: Ctx, who: str, branch_id: int | None) -> GroupInfo:
    if re.search(r"\d", who or ""):
        gi = ctx.groups.get(group_key(who))
        if gi is None:
            raise RowError(f"группа {who.strip()} не найдена — импортируйте сначала файлы групп")
        return gi
    st = _one_student(ctx, person_words(who), branch_id)
    gi = await _individual_group(ctx, st.id)
    if gi is None:
        raise RowError(f"индивидуальные занятия «{who}» не найдены — импортируйте сначала индивидуальные")
    return gi


async def step_schedule(ctx: Ctx, r: dict, seen: set) -> RowResult:
    label = f"{r['who']} · {r['room']} · {r['start']:%H:%M}" if r["start"] else f"{r['who']} · {r['room']}"
    branch_id = ctx.branch_id(r["branch"])
    if branch_id is None:
        raise RowError(f"филиал «{r['branch']}» не найден")
    gi = await _group_for(ctx, r["who"], branch_id)
    dup = (gi.id, tuple(r["weekdays"]), r["start"])
    if dup in seen:
        return RowResult(r["row"], "skip", label, "та же запись в другой день недели")
    seen.add(dup)
    room_id = ctx.room_id(branch_id, r["room"])
    # The same days at another time: the room schedule and the group card disagree. Keep what the group has and say so,
    # rather than doubling the group's lessons.
    clash = next((x for x in await ctx.db.scalars(select(ScheduleRule).where(ScheduleRule.group_id == gi.id,
                                                                             ScheduleRule.archived_at.is_(None)))
                  if set(x.weekdays) & set(r["weekdays"]) and x.start_time != r["start"]), None)
    if clash is not None:
        return RowResult(r["row"], "skip", label, f"в карточке группы другое время: {_days(clash.weekdays)} "
                         f"{clash.start_time:%H:%M}–{clash.end_time:%H:%M}; оставлено оно — проверьте вручную")
    status, note = await ensure_rule(ctx, gi.id, r["weekdays"], r["start"], r["end"], room_id, r["since"])
    if status == "new":
        await ref_put(ctx, "rule", f"{gi.id}|{_days(r['weekdays'])}|{r['start']}", "group", gi.id)
    return RowResult(r["row"], status, label, note)


# ---------- step: attendance ----------
async def _lesson_on(ctx: Ctx, gi: GroupInfo, d: date) -> tuple[int, bool]:
    """The group's lesson on that school day: an existing one, or a held lesson at the group's usual time."""
    db = ctx.db
    start, end = at_local(d, time(0)), at_local(d + timedelta(days=1), time(0))
    lesson = await db.scalar(select(Lesson).where(Lesson.group_id == gi.id, Lesson.starts_at >= start, Lesson.starts_at < end,
                                                  Lesson.status != LessonStatus.CANCELLED).order_by(Lesson.starts_at).limit(1))
    if lesson is not None:
        if lesson.status == LessonStatus.PLANNED and lesson.starts_at <= now():
            lesson.status = LessonStatus.DONE
            lesson.attendance_marked_at = lesson.attendance_marked_at or now()
        return lesson.id, False
    rules = list(await db.scalars(select(ScheduleRule).where(ScheduleRule.group_id == gi.id).order_by(ScheduleRule.id)))
    rule = next((x for x in rules if d.weekday() in x.weekdays), rules[0] if rules else None)
    room_id = rule.room_id if rule else gi.room_id
    if room_id is None:
        raise RowError("у группы нет аудитории и расписания — занятие не создать")
    st, en = (rule.start_time, rule.end_time) if rule else (time(9, 0), time(10, 0))
    lesson = Lesson(branch_id=gi.branch_id, group_id=gi.id, level_id=gi.level_id, teacher_id=gi.teacher_id, room_id=room_id,
                    rule_id=rule.id if rule else None, starts_at=at_local(d, st), ends_at=at_local(d, en),
                    status=LessonStatus.DONE, attendance_marked_at=now(), topic="Перенесено из старой CRM")
    db.add(lesson)
    await db.flush()
    await ref_put(ctx, "lesson", f"{gi.id}|{d.isoformat()}", "lesson", lesson.id)
    ctx.stats["lessons_held"] += 1
    return lesson.id, True


async def step_attendance(ctx: Ctx, r: dict) -> RowResult:
    db = ctx.db
    label = f"{r['block'].strip()} · {r['student']}"
    if not r["marks"]:
        return RowResult(r["row"], "skip", label, "нет отметок")
    branch_id = ctx.branch_id(r["branch"])
    gi = await _group_for(ctx, r["block"], branch_id)
    words = person_words(r["student"])
    members = set((await db.scalars(select(GroupMember.student_id).where(GroupMember.group_id == gi.id))).all())
    found = [s for s in ctx.students_named(words, gi.branch_id) if s.id in members] or ctx.students_named(words, gi.branch_id)
    if len(found) != 1:
        raise RowError(f"ученик «{r['student']}» " + ("не найден" if not found else "встречается несколько раз") + " в этом филиале")
    sid = found[0].id
    created = changed = same = future = 0
    first_day: date | None = None
    last_visit: date | None = None
    for ds, status in r["marks"].items():
        d = date.fromisoformat(ds)
        if d > ctx.today:
            future += 1
            continue
        lesson_id, _ = await _lesson_on(ctx, gi, d)
        a = await db.scalar(select(Attendance).where(Attendance.lesson_id == lesson_id, Attendance.student_id == sid))
        if a is None:
            # Not charged: lesson balances come from the old CRM, the marks are history.
            db.add(Attendance(lesson_id=lesson_id, student_id=sid, status=status, charged=False, marked_by=ctx.actor.id))
            created += 1
        elif a.status != status:
            a.status = status
            changed += 1
        else:
            same += 1
        first_day = min(first_day or d, d)
        if status == "present":
            last_visit = max(last_visit or d, d)
    await db.flush()
    if first_day is not None:
        # The roster shows members from their joining day: make sure the imported marks are visible.
        m = await db.scalar(select(GroupMember).where(GroupMember.group_id == gi.id, GroupMember.student_id == sid,
                                                      GroupMember.left_on.is_(None)))
        if m is None:
            await add_member(ctx, gi, sid, first_day)
        elif m.joined_on > first_day:
            m.joined_on = first_day
    if last_visit:
        s = await db.get(Student, sid)
        lv = at_local(last_visit, time(12, 0))
        if s.last_visit_at is None or s.last_visit_at < lv:
            s.last_visit_at = lv
    ctx.stats["marks_created"] += created
    ctx.stats["marks_updated"] += changed
    note = [f"отметок: новых {created}" + (f", изменено {changed}" if changed else "") + (f", без изменений {same}" if same else "")]
    if future:
        note.append(f"{future} отметок на будущие даты не перенесены")
    status = "new" if created else "update" if changed else "skip"
    return RowResult(r["row"], status, label, "; ".join(note))


# ---------- step: payments ----------
async def run_payments(ctx: Ctx, parsed: Parsed) -> list[RowResult]:
    """Payments are thousands of independent inserts: every row is checked first, then the new ones go in with one
    batched INSERT (and one for their import refs) instead of a savepoint and two round trips per row."""
    db = ctx.db
    out: list[RowResult] = []
    new: list[tuple[dict, Payment, str, RowResult]] = []
    seen: set[str] = set()
    student_level = dict((await db.execute(select(Student.id, Student.level_id))).all())
    for r in parsed.rows:
        inv = r["invoice"] or f"{r['client_id']}|{r['paid_on']}|{r['amount']}"
        label = f"Счёт №{r['invoice'] or '—'} · {r['payer'] or ''} · {r['amount'] or 0} ₸"
        if not _paid(r):
            out.append(RowResult(r["row"], "skip", label, f"не оплачен в старой CRM («{r['state']}»)"))
            continue
        if r["amount"] is None or r["amount"] < 0:
            out.append(RowResult(r["row"], "error", label, "нет суммы"))
            continue
        if inv in seen:
            out.append(RowResult(r["row"], "skip", label, "повтор счёта в файле"))
            continue
        seen.add(inv)
        if (ref := await ref_get(ctx, "payment", inv)) is not None:
            p = await db.get(Payment, ref.entity_id)
            reason = (f"уже перенесён, но сумма изменилась ({p.amount} → {r['amount']}) — проверьте вручную"
                      if p is not None and p.amount != r["amount"] else "уже перенесён")
            out.append(RowResult(r["row"], "skip", label, reason))
            continue
        sid = ref_entity(ctx, "student", r["client_id"] or "")
        if sid is None or sid not in ctx.students:
            out.append(RowResult(r["row"], "error", label, f"ученик с ИД клиента {r['client_id']} не импортирован"))
            continue
        paid_on = r["paid_on"] or r["created"]
        if paid_on is None:
            out.append(RowResult(r["row"], "error", label, "нет даты оплаты"))
            continue
        books = _is_books(r)
        note = f"Старая CRM, счёт №{r['invoice']}" if r["invoice"] else "Старая CRM"
        if r["comment"]:
            note += f": {r['comment']}"
        if r["received_by"]:
            note += f". Принял: {r['received_by']}"
        # History only: no lessons added, no balance change, not «first payment» (no KPI), no message to the parents.
        p = Payment(student_id=sid, branch_id=ctx.branch_id(r["branch"]) or ctx.students[sid].branch_id,
                    level_id=None if books else student_level.get(sid), category="book" if books else "course",
                    amount=r["amount"], discount=0, lessons=0, lesson_price=0, method=METHODS.get(norm(r["method"]), "cash"),
                    received_by=ctx.actor.id, paid_at=at_local(paid_on, time(12, 0)), refunded=0, is_first=False,
                    note=note[:255], source=SOURCE)
        res = RowResult(r["row"], "new", label, "учебные материалы" if books else None)
        new.append((r, p, inv, res))
        out.append(res)
    if new:
        db.add_all([p for _, p, _, _ in new])
        await db.flush()
        db.add_all([ImportRef(kind="payment", ext_key=inv[:255], entity="payment", entity_id=p.id, fingerprint=fingerprint(r), meta={})
                    for r, p, inv, _ in new])
        await db.flush()
        last: dict[int, object] = {}
        for _, p, _, _ in new:
            if p.student_id not in last or last[p.student_id] < p.paid_at:
                last[p.student_id] = p.paid_at
        for sid, at in last.items():
            s = await db.get(Student, sid)
            if s.last_payment_at is None or s.last_payment_at < at:
                s.last_payment_at = at
        await db.flush()
        ctx.stats["payments"] += len(new)
        ctx.stats["payments_sum"] += sum(p.amount for _, p, _, _ in new)
    return sorted(out, key=lambda x: x.row)


# ---------- step: library ----------
async def step_book(ctx: Ctx, r: dict) -> RowResult:
    db = ctx.db
    label = r["title"]
    key = norm(r["title"])
    fp = fingerprint(r)
    ref = await ref_get(ctx, "book", key)
    if ref and ref.fingerprint == fp:
        return RowResult(r["row"], "skip", label, "без изменений")
    notes = []
    bid = ref.entity_id if ref else await db.scalar(select(Book.id).where(func.lower(Book.title) == key, Book.archived_at.is_(None)))
    if bid is None:
        b = Book(title=r["title"][:255], level_id=ctx.level_id(r["title"]), sale_price=r["price"], purchase_price=0)
        db.add(b)
        await db.flush()
        bid, result = b.id, "new"
        ctx.stats["books"] += 1
    else:
        b = await db.get(Book, bid)
        if r["price"] and b.sale_price != r["price"]:
            b.sale_price = r["price"]
            notes.append("цена")
        result = "update"
    qty = (r["for_lend"] or 0) + (r["for_sale"] or 0)
    branch_id = ctx.default_branch_id
    sref = await ref_get(ctx, "book_stock", key)
    if qty and branch_id is None:
        notes.append(f"остаток {qty} шт. не перенесён: в файле нет филиала — выберите филиал по умолчанию")
    elif qty and sref is None:
        stock = await db.scalar(select(BookStock).where(BookStock.branch_id == branch_id, BookStock.book_id == bid))
        if stock is None:
            stock = BookStock(branch_id=branch_id, book_id=bid, qty=0)
            db.add(stock)
        stock.qty += qty
        db.add(BookMovement(at=now(), kind="in", branch_id=branch_id, book_id=bid, qty=qty, unit_price=0,
                            reason="Остаток из старой CRM", actor_id=ctx.actor.id))
        await db.flush()
        await ref_put(ctx, "book_stock", key, "book", bid, meta={"qty": qty, "branch_id": branch_id})
        notes.append(f"остаток {qty} шт. → {ctx.branch_names.get(branch_id, '')}")
    elif qty and sref is not None and (sref.meta or {}).get("qty") != qty:
        notes.append(f"остаток уже перенесён ({(sref.meta or {}).get('qty')} шт.), в файле {qty} — проверьте вручную")
    await ref_put(ctx, "book", key, "book", bid, fp, ref=ref)
    if r["sold"]:
        notes.append(f"продано в старой CRM: {r['sold']} (история продаж — в платежах «Учебные материалы»)")
    return RowResult(r["row"], result, label, "; ".join(notes) or None)


# ---------- step: communications ----------
async def step_communication(ctx: Ctx, r: dict) -> RowResult:
    db = ctx.db
    label = f"{r['student'] or '—'} · {r['at']:%d.%m.%Y %H:%M}" if r["at"] else (r["student"] or "—")
    key = fingerprint({"at": r["at"], "student": r["student"], "text": r["text"]})
    if await ref_get(ctx, "communication", key):
        return RowResult(r["row"], "skip", label, "уже перенесено")
    if r["student_id"]:
        sref = await ref_get(ctx, "student", r["student_id"])
        sid = sref.entity_id if sref else None
    else:
        sid = None
    when = f"{r['at']:%d.%m.%Y %H:%M}" if r["at"] else ""
    line = f"[{when}] {r['channel'] or ''}, {(r['direction'] or '').lower()}, {r['who'] or ''}: {r['text'] or ''}".strip()
    found = ctx.students_named(person_words(r["student"])) if sid is None else []
    if sid is None and len(found) == 1:
        sid = found[0].id
    if sid is not None:
        s = await db.get(Student, sid)
        s.notes = _note_join(s.notes, line)
        await ref_put(ctx, "communication", key, "student", s.id)
        return RowResult(r["row"], "new", label, "в заметки ученика")
    if len(found) > 1:
        raise RowError(f"несколько учеников с именем «{r['student']}» — не перенесено")
    # Not a student: a contact of the old CRM's sales. It becomes a CRM lead with this history, in «Отказ» so that it
    # pings nobody (new leads alert managers within the hour); a manager can move it back to work.
    branch_id = ctx.default_branch_id
    if branch_id is None:
        raise RowError("не ученик: чтобы создать лид, выберите филиал по умолчанию")
    lead_key = norm(r["student"]) or key
    lid = ref_entity(ctx, "lead", lead_key)
    if lid is None:
        lead = await create_lead(db, full_name=(r["student"] or "Контакт из старой CRM")[:255], phone=r["phone"], branch_id=branch_id,
                                 source=LeadSource.IMPORT, owner_id=None, stage="lost", notify=False,
                                 lost_reason="Перенесено из старой CRM — история контактов")
        lid = lead.id
        await ref_put(ctx, "lead", lead_key, "lead", lid)
        result_note = "создан лид (в «Отказ», без уведомлений)"
    else:
        result_note = "в историю лида"
    db.add(LeadEvent(lead_id=lid, at=at_local(r["at"].date(), r["at"].time()) if r["at"] else now(), kind="note", text=line[:4000],
                     actor_id=ctx.actor.id, meta={"source": SOURCE}))
    await ref_put(ctx, "communication", key, "lead", lid)
    return RowResult(r["row"], "new", label, result_note)


def _unsupported(kind: str):
    async def step(ctx: Ctx, r: dict) -> RowResult:
        return RowResult(r["row"], "skip", " · ".join(v for v in r["values"][:3] if v), f"«{KINDS[kind].title}» не переносятся")
    return step


ROW_STEPS: dict[str, Callable[..., Awaitable[RowResult]]] = {
    "teachers": step_teacher, "groups": step_group, "students": step_student, "individual": step_individual,
    "attendance": step_attendance, "library": step_book, "communications": step_communication,
    "test_results": _unsupported("test_results"), "homework_plans": _unsupported("homework_plans"),
}


def _label(kind: str, r: dict) -> str:
    """The same label the step itself shows, for rows that failed before getting one."""
    if kind == "groups":
        return f"Группа {r['name']}"
    if kind == "individual":
        return f"Индивидуально: {r['short_name']}"
    if kind == "attendance":
        return f"{r['block'].strip()} · {r['student']}"
    if kind == "schedule":
        return f"{r['who']} · {r['room']} · {r['start']:%H:%M}" if r.get("start") else f"{r['who']} · {r['room']}"
    if kind == "communications":
        return f"{r['student'] or '—'} · {r['at']:%d.%m.%Y %H:%M}" if r.get("at") else (r.get("student") or "—")
    for k in ("full_name", "title", "student", "payer"):
        if r.get(k):
            return str(r[k])
    return f"строка {r.get('row')}"


async def run_rows(ctx: Ctx, kind: str, parsed: Parsed) -> list[RowResult]:
    if kind == "payments":
        return await run_payments(ctx, parsed)
    out: list[RowResult] = []
    seen: set = set()
    for r in parsed.rows:
        ctx.pending.clear()
        try:
            async with ctx.db.begin_nested():
                res = await (step_schedule(ctx, r, seen) if kind == "schedule" else ROW_STEPS[kind](ctx, r))
            for fn in ctx.pending:
                fn()
        except RowError as e:
            res = RowResult(r["row"], "error", _label(kind, r), str(e))
        except HTTPException as e:
            res = RowResult(r["row"], "error", _label(kind, r), str(e.detail))
        except Exception as e:  # noqa: BLE001 — one bad row must not stop the file; the reason is shown to the owner
            res = RowResult(r["row"], "error", _label(kind, r), f"не удалось записать: {type(e).__name__}")
        ctx.pending.clear()
        out.append(res)
    for e in parsed.errors:
        out.append(RowResult(e["row"], "error", f"строка {e['row']}", e["reason"]))
    return out

