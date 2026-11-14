from datetime import UTC, datetime

from fastapi import APIRouter
from pydantic import Field
from sqlalchemy import func, select

from app.core.audit import diff, snapshot, write_audit
from app.core.deps import DB, Actor, CurrentActor, require, require_staff
from app.core.errors import bad_request, forbidden, not_found
from app.core.permissions import NETWORK
from app.core.schemas import In, ORM
from app.models import Branch, Group, Level, Role, Room, User, UserBranch, UserRole
from app.models.identity import UserKind

router = APIRouter(tags=["org"])


class BranchIn(In):
    name: str = Field(min_length=2, max_length=120)
    address: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=32)
    hours: str | None = Field(default=None, max_length=255)
    admin_id: int | None = None


class BranchOut(ORM):
    id: int
    name: str
    address: str | None
    phone: str | None
    hours: str | None
    admin_id: int | None
    archived_at: datetime | None


class RoomIn(In):
    name: str = Field(min_length=1, max_length=64)
    capacity: int = Field(ge=1, le=200)
    equipment: str | None = Field(default=None, max_length=255)
    status: str = Field(default="active", pattern="^(active|repair)$")


class RoomOut(ORM):
    id: int
    branch_id: int
    name: str
    capacity: int
    equipment: str | None
    status: str
    archived_at: datetime | None


class LevelIn(In):
    name: str = Field(max_length=255)
    # Optional: generated on create when the level is added from the dictionaries page; kept as is on edit.
    code: str | None = Field(default=None, pattern=r"^[A-Z0-9_-]{2,32}$")
    color: str = Field(default="#1A6FD1", pattern=r"^#[0-9A-Fa-f]{6}$")
    lesson_price: int = Field(ge=0)
    order: int = 0
    track: str = Field(default="adults", pattern="^(adults|kids|exam)$")
    duration_months: int = 3
    next_level_id: int | None = None


class LevelOut(ORM):
    id: int
    name: str
    code: str
    color: str
    lesson_price: int
    order: int
    track: str
    duration_months: int
    next_level_id: int | None
    is_kids: bool
    archived_at: datetime | None


@router.get("/branches", response_model=list[BranchOut])
async def branches(db: DB, actor: CurrentActor) -> list[BranchOut]:
    # Any signed-in staff sees the branch list (names are needed everywhere); students/parents don't need it.
    rows = await db.scalars(select(Branch).where(Branch.archived_at.is_(None)).order_by(Branch.id))
    return [BranchOut.model_validate(b) for b in rows]


@router.post("/branches", response_model=BranchOut, status_code=201)
async def create_branch(body: BranchIn, db: DB, actor: Actor = require("branches", "create")) -> BranchOut:
    if actor.scope("branches", "create") != NETWORK:
        raise forbidden("Новый филиал создаёт только руководитель сети")
    b = Branch(**body.model_dump())
    db.add(b)
    await db.flush()
    await write_audit(db, actor_id=actor.id, action="branch.create", entity="branch", entity_id=b.id, branch_id=b.id,
                      ip=actor.ip, after=snapshot(b))
    await db.commit()
    return BranchOut.model_validate(b)


@router.patch("/branches/{branch_id}", response_model=BranchOut)
async def update_branch(branch_id: int, body: BranchIn, db: DB, actor: Actor = require("branches", "edit")) -> BranchOut:
    b = await db.get(Branch, branch_id)
    if b is None:
        raise not_found("Филиал")
    actor.ensure_branch("branches", "edit", b.id)
    before = snapshot(b)
    data = body.model_dump()
    if actor.scope("branches", "edit") != NETWORK:
        data.pop("admin_id")  # who runs the branch is decided by the network owner
    for k, v in data.items():
        setattr(b, k, v)
    bb, aa = diff(before, snapshot(b))
    await write_audit(db, actor_id=actor.id, action="branch.update", entity="branch", entity_id=b.id, branch_id=b.id,
                      ip=actor.ip, before=bb, after=aa)
    await db.commit()
    return BranchOut.model_validate(b)


@router.get("/branches/{branch_id}/rooms", response_model=list[RoomOut])
async def rooms(branch_id: int, db: DB, actor: CurrentActor) -> list[RoomOut]:
    rows = await db.scalars(select(Room).where(Room.branch_id == branch_id, Room.archived_at.is_(None)).order_by(Room.name))
    return [RoomOut.model_validate(r) for r in rows]


@router.post("/branches/{branch_id}/rooms", response_model=RoomOut, status_code=201)
async def create_room(branch_id: int, body: RoomIn, db: DB, actor: Actor = require("branches", "create")) -> RoomOut:
    actor.ensure_branch("branches", "create", branch_id)
    if await db.get(Branch, branch_id) is None:
        raise not_found("Филиал")
    r = Room(branch_id=branch_id, **body.model_dump())
    db.add(r)
    await db.flush()
    await write_audit(db, actor_id=actor.id, action="room.create", entity="room", entity_id=r.id, branch_id=branch_id,
                      ip=actor.ip, after=snapshot(r))
    await db.commit()
    return RoomOut.model_validate(r)


@router.patch("/rooms/{room_id}", response_model=RoomOut)
async def update_room(room_id: int, body: RoomIn, db: DB, actor: Actor = require("branches", "edit")) -> RoomOut:
    r = await db.get(Room, room_id)
    if r is None:
        raise not_found("Кабинет")
    actor.ensure_branch("branches", "edit", r.branch_id)
    before = snapshot(r)
    for k, v in body.model_dump().items():
        setattr(r, k, v)
    bb, aa = diff(before, snapshot(r))
    await write_audit(db, actor_id=actor.id, action="room.update", entity="room", entity_id=r.id, branch_id=r.branch_id,
                      ip=actor.ip, before=bb, after=aa)
    await db.commit()
    return RoomOut.model_validate(r)


@router.post("/rooms/{room_id}/archive", status_code=204)
async def archive_room(room_id: int, db: DB, actor: Actor = require("branches", "archive")) -> None:
    r = await db.get(Room, room_id)
    if r is None:
        raise not_found("Кабинет")
    actor.ensure_branch("branches", "archive", r.branch_id)
    r.archived_at = datetime.now(UTC)
    await write_audit(db, actor_id=actor.id, action="room.archive", entity="room", entity_id=r.id, branch_id=r.branch_id, ip=actor.ip)
    await db.commit()


@router.get("/levels", response_model=list[LevelOut])
async def levels(db: DB, actor: CurrentActor) -> list[LevelOut]:
    rows = await db.scalars(select(Level).where(Level.archived_at.is_(None)).order_by(Level.order))
    return [LevelOut.model_validate(lv) for lv in rows]


@router.post("/levels", response_model=LevelOut, status_code=201)
async def create_level(body: LevelIn, db: DB, actor: Actor = require("settings", "edit")) -> LevelOut:
    if body.code and await db.scalar(select(Level).where(Level.code == body.code)):
        raise bad_request("Уровень с таким кодом уже есть")
    code = body.code or f"L{(await db.scalar(select(func.coalesce(func.max(Level.id), 0)))) + 1}"
    while await db.scalar(select(Level.id).where(Level.code == code)):
        code += "X"
    lv = Level(**body.model_dump(exclude={"code"}), code=code, is_kids=body.track == "kids")
    db.add(lv)
    await db.flush()
    await write_audit(db, actor_id=actor.id, action="level.create", entity="level", entity_id=lv.id, ip=actor.ip, after=snapshot(lv))
    await db.commit()
    return LevelOut.model_validate(lv)


@router.patch("/levels/{level_id}", response_model=LevelOut)
async def update_level(level_id: int, body: LevelIn, db: DB, actor: Actor = require("settings", "edit")) -> LevelOut:
    """A price change applies to future payments only: paid lessons keep their price in the ledger."""
    lv = await db.get(Level, level_id)
    if lv is None:
        raise not_found("Уровень")
    before = snapshot(lv)
    if body.code and body.code != lv.code and await db.scalar(select(Level.id).where(Level.code == body.code)):
        raise bad_request("Уровень с таким кодом уже есть")
    for k, v in body.model_dump(exclude={"code"} if not body.code else set()).items():
        setattr(lv, k, v)
    lv.is_kids = lv.track == "kids"
    bb, aa = diff(before, snapshot(lv))
    await write_audit(db, actor_id=actor.id, action="level.update", entity="level", entity_id=lv.id, ip=actor.ip, before=bb, after=aa)
    await db.commit()
    return LevelOut.model_validate(lv)


@router.post("/levels/{level_id}/archive", status_code=204)
async def archive_level(level_id: int, db: DB, actor: Actor = require("settings", "edit")) -> None:
    """Archived, never deleted: students and payments keep their level. Not while active groups study at it."""
    lv = await db.get(Level, level_id)
    if lv is None or lv.archived_at is not None:
        raise not_found("Уровень")
    if await db.scalar(select(Group.id).where(Group.level_id == lv.id, Group.archived_at.is_(None)).limit(1)):
        raise bad_request("На этом уровне есть действующие группы — сначала закройте или переведите их")
    lv.archived_at = datetime.now(UTC)
    await write_audit(db, actor_id=actor.id, action="level.archive", entity="level", entity_id=lv.id, ip=actor.ip,
                      before={"name": lv.name})
    await db.commit()


@router.get("/staff-directory")
async def staff_directory(db: DB, actor: Actor = require_staff(), role: str | None = None,
                          branch_id: int | None = None) -> list[dict]:
    """Light list of colleagues for pickers (teacher, assignee): names and branches only — no phones, no salary."""
    q = select(User).where(User.kind == UserKind.STAFF, User.is_active.is_(True), User.archived_at.is_(None))
    if role:
        q = q.where(User.id.in_(select(UserRole.user_id).join(Role, Role.id == UserRole.role_id).where(Role.code == role)))
    if branch_id:
        if not actor.is_owner and branch_id not in actor.branch_ids:
            raise forbidden("Нет доступа к этому филиалу")
        q = q.where(User.id.in_(select(UserBranch.user_id).where(UserBranch.branch_id == branch_id)))
    elif not actor.is_owner:
        q = q.where(User.id.in_(select(UserBranch.user_id).where(UserBranch.branch_id.in_(actor.branch_ids or {-1}))))
    return [{"id": u.id, "full_name": u.full_name, "position": u.position, "branch_ids": sorted(b.branch_id for b in u.branches),
             "roles": sorted(ur.role.code for ur in u.roles)} for u in await db.scalars(q.order_by(User.full_name).limit(500))]
