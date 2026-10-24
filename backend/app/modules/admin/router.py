"""Role builder, staff, security overview, audit log, settings and rates."""

from datetime import UTC, date, datetime

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, select

from app.core.audit import diff, snapshot, write_audit
from app.core.deps import DB, Actor, require
from app.core.errors import bad_request, conflict, forbidden, not_found
from app.core.permissions import CATALOG, NETWORK, SCOPES, SYSTEM_ROLE_CODES, is_valid, wider
from app.core.query import paginate
from app.core.schemas import ORM, Page
from app.core.security import hash_password, mask_phone, normalize_phone, validate_password_strength
from app.models import AuditLog, AuthSession, RateSetting, Role, RolePermission, Setting, User, UserBranch, UserRole
from app.models.identity import UserKind
from app.modules.auth.service import revoke_all

router = APIRouter(tags=["admin"])


# ---------- roles ----------
class PermIn(BaseModel):
    module: str
    action: str
    scope: str = "branch"


class RoleIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    code: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]{1,40}$")
    description: str | None = None
    coin_limit: int = Field(default=0, ge=0, le=100000)
    permissions: list[PermIn] = []


class PermOut(ORM):
    module: str
    action: str
    scope: str


class RoleOut(ORM):
    id: int
    name: str
    code: str
    description: str | None
    is_system: bool
    coin_limit: int
    archived_at: datetime | None
    permissions: list[PermOut]
    members: int = 0


def _check_grantable(actor: Actor, perms: list[PermIn]) -> None:
    """Nobody can hand out more than they have themselves (privilege escalation guard)."""
    for p in perms:
        if not is_valid(p.module, p.action) or p.scope not in SCOPES:
            raise bad_request(f"Неизвестное право {p.module}.{p.action}:{p.scope}")
        if actor.is_owner:
            continue
        mine = actor.grants.scope(p.module, p.action)
        if mine is None or wider(mine, p.scope) != mine:
            raise forbidden(f"Нельзя выдать право шире собственного: {p.module}.{p.action}")


async def _ensure_outranks(db: DB, actor: Actor, target: User) -> None:
    """Managing an account (password, profile, archive) needs every right that account has, at least as wide —
    otherwise resetting a password would be a way to borrow someone's bigger rights."""
    if actor.is_owner:
        return
    perms = await db.execute(select(RolePermission.module, RolePermission.action, RolePermission.scope)
                             .join(UserRole, UserRole.role_id == RolePermission.role_id).where(UserRole.user_id == target.id))
    for module, action, scope in perms:
        mine = actor.grants.scope(module, action)
        if mine is None or wider(mine, scope) != mine:
            raise forbidden("У сотрудника есть права шире ваших — обратитесь к руководителю")


@router.get("/roles", response_model=list[RoleOut])
async def list_roles(db: DB, actor: Actor = require("roles", "view")) -> list[RoleOut]:
    roles = list(await db.scalars(select(Role).order_by(Role.is_system.desc(), Role.id)))
    counts: dict[int, int] = {}
    for rid in (await db.scalars(select(UserRole.role_id))).all():
        counts[rid] = counts.get(rid, 0) + 1
    out = []
    for r in roles:
        o = RoleOut.model_validate(r)
        o.members = counts.get(r.id, 0)
        out.append(o)
    return out


@router.post("/roles", response_model=RoleOut, status_code=201)
async def create_role(body: RoleIn, db: DB, actor: Actor = require("roles", "manage")) -> RoleOut:
    _check_grantable(actor, body.permissions)
    code = body.code or f"role_{int(datetime.now(UTC).timestamp())}"
    if await db.scalar(select(Role).where(Role.code == code)):
        raise conflict("Роль с таким кодом уже есть")
    role = Role(name=body.name, code=code, description=body.description, coin_limit=body.coin_limit)
    role.permissions = [RolePermission(module=p.module, action=p.action, scope=p.scope) for p in body.permissions]
    db.add(role)
    await db.flush()
    await write_audit(db, actor_id=actor.id, action="role.create", entity="role", entity_id=role.id, ip=actor.ip,
                      after={"name": role.name, "permissions": [f"{p.module}.{p.action}:{p.scope}" for p in body.permissions]})
    await db.commit()
    await db.refresh(role)
    return RoleOut.model_validate(role)


@router.put("/roles/{role_id}", response_model=RoleOut)
async def update_role(role_id: int, body: RoleIn, db: DB, actor: Actor = require("roles", "manage")) -> RoleOut:
    role = await db.get(Role, role_id)
    if role is None:
        raise not_found("Роль")
    if role.code == "owner":
        raise forbidden("Права супер-админа не редактируются")
    if role.is_system and not actor.is_owner:
        raise forbidden("Системные роли меняет только супер-админ")
    if role.code in actor.role_codes and not actor.is_owner:
        raise forbidden("Нельзя менять права собственной роли")
    _check_grantable(actor, body.permissions)
    before = sorted(f"{p.module}.{p.action}:{p.scope}" for p in role.permissions)
    role.name, role.description, role.coin_limit = body.name, body.description, body.coin_limit
    role.permissions.clear()
    await db.flush()
    role.permissions.extend(RolePermission(module=p.module, action=p.action, scope=p.scope) for p in body.permissions)
    after = sorted(f"{p.module}.{p.action}:{p.scope}" for p in body.permissions)
    await write_audit(db, actor_id=actor.id, action="role.update", entity="role", entity_id=role.id, ip=actor.ip,
                      before={"permissions": before}, after={"name": role.name, "permissions": after})
    await db.commit()
    await db.refresh(role)
    return RoleOut.model_validate(role)


@router.post("/roles/{role_id}/archive", status_code=204)
async def archive_role(role_id: int, db: DB, actor: Actor = require("roles", "manage")) -> None:
    role = await db.get(Role, role_id)
    if role is None:
        raise not_found("Роль")
    if role.is_system or role.code in SYSTEM_ROLE_CODES:
        raise forbidden("Системную роль нельзя архивировать")
    role.archived_at = datetime.now(UTC)
    await write_audit(db, actor_id=actor.id, action="role.archive", entity="role", entity_id=role.id, ip=actor.ip)
    await db.commit()


@router.get("/permissions/catalog")
async def catalog(actor: Actor = require("roles", "view")) -> dict:
    return {m: {"title": t, "actions": acts} for m, (t, acts) in CATALOG.items()}


# ---------- staff ----------
class StaffIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=255)
    phone: str
    email: str | None = None
    position: str | None = None
    salary: int = Field(default=0, ge=0)
    password: str | None = None
    role_ids: list[int] = []
    branch_ids: list[int] = []


class StaffPatch(BaseModel):
    full_name: str | None = None
    email: str | None = None
    position: str | None = None
    salary: int | None = Field(default=None, ge=0)
    role_ids: list[int] | None = None
    branch_ids: list[int] | None = None
    is_active: bool | None = None


class StaffOut(BaseModel):
    id: int
    full_name: str
    phone: str | None
    position: str | None
    salary: int | None
    is_active: bool
    totp_enabled: bool
    last_login_at: datetime | None
    roles: list[dict]
    branch_ids: list[int]
    archived_at: datetime | None


def staff_out(u: User, actor: Actor) -> StaffOut:
    see_salary = actor.can("payroll", "view") and actor.scope("payroll", "view") != "own"
    return StaffOut(
        id=u.id, full_name=u.full_name,
        phone=u.phone if actor.can("students", "view_contacts") or actor.is_owner else mask_phone(u.phone),
        position=u.position, salary=u.salary if see_salary or u.id == actor.id else None,
        is_active=u.is_active, totp_enabled=u.totp_enabled, last_login_at=u.last_login_at,
        roles=[{"id": ur.role.id, "name": ur.role.name, "code": ur.role.code} for ur in u.roles],
        branch_ids=[b.branch_id for b in u.branches], archived_at=u.archived_at,
    )


async def _check_assignable(db: DB, actor: Actor, role_ids: list[int], branch_ids: list[int]) -> list[Role]:
    roles = list(await db.scalars(select(Role).where(Role.id.in_(role_ids)))) if role_ids else []
    if len(roles) != len(set(role_ids)):
        raise bad_request("Роль не найдена")
    for r in roles:
        if r.archived_at:
            raise bad_request(f"Роль «{r.name}» в архиве")
        if r.code == "owner" and not actor.is_owner:
            raise forbidden("Назначить супер-админа может только супер-админ")
        _check_grantable(actor, [PermIn(module=p.module, action=p.action, scope=p.scope) for p in r.permissions])
    allowed = actor.branches_for("staff", "edit")
    if allowed is not None and not set(branch_ids) <= allowed:
        raise forbidden("Нельзя назначить чужой филиал")
    return roles


def _staff_visible(actor: Actor, u: User) -> bool:
    allowed = actor.branches_for("staff", "view")
    return allowed is None or bool({b.branch_id for b in u.branches} & allowed) or u.id == actor.id


@router.get("/staff", response_model=Page[StaffOut])
async def list_staff(
    db: DB, actor: Actor = require("staff", "view"), q: str | None = None, branch_id: int | None = None,
    role: str | None = None, archived: bool = False, limit: int = 50, offset: int = 0,
) -> Page[StaffOut]:
    stmt = select(User).where(User.kind == UserKind.STAFF)
    stmt = stmt.where(User.archived_at.is_not(None) if archived else User.archived_at.is_(None))
    allowed = actor.branches_for("staff", "view")
    if allowed is not None:
        stmt = stmt.where(User.id.in_(select(UserBranch.user_id).where(UserBranch.branch_id.in_(allowed))))
    if branch_id:
        stmt = stmt.where(User.id.in_(select(UserBranch.user_id).where(UserBranch.branch_id == branch_id)))
    if role:
        stmt = stmt.where(User.id.in_(select(UserRole.user_id).join(Role).where(Role.code == role)))
    if q:
        stmt = stmt.where(User.full_name.ilike(f"%{q}%"))
    rows, total = await paginate(db, stmt.order_by(User.full_name), limit, offset)
    return Page(items=[staff_out(u, actor) for u in rows], total=total, limit=limit, offset=offset)


@router.post("/staff", response_model=StaffOut, status_code=201)
async def create_staff(body: StaffIn, db: DB, actor: Actor = require("staff", "create")) -> StaffOut:
    phone = normalize_phone(body.phone)
    if await db.scalar(select(User).where(User.phone == phone)):
        raise conflict("Пользователь с таким телефоном уже есть")
    roles = await _check_assignable(db, actor, body.role_ids, body.branch_ids)
    if body.password and (err := validate_password_strength(body.password)):
        raise bad_request(err)
    u = User(kind=UserKind.STAFF, full_name=body.full_name, phone=phone, email=body.email, position=body.position,
             salary=body.salary, password_hash=hash_password(body.password) if body.password else None)
    db.add(u)
    await db.flush()
    for r in roles:
        db.add(UserRole(user_id=u.id, role_id=r.id))
    for b in set(body.branch_ids):
        db.add(UserBranch(user_id=u.id, branch_id=b))
    await write_audit(db, actor_id=actor.id, action="staff.create", entity="user", entity_id=u.id, ip=actor.ip,
                      after={"full_name": u.full_name, "roles": [r.code for r in roles], "branches": body.branch_ids})
    await db.commit()
    u = await db.scalar(select(User).where(User.id == u.id).execution_options(populate_existing=True))
    return staff_out(u, actor)


@router.patch("/staff/{user_id}", response_model=StaffOut)
async def update_staff(user_id: int, body: StaffPatch, db: DB, actor: Actor = require("staff", "edit")) -> StaffOut:
    u = await db.get(User, user_id, populate_existing=True)
    if u is None or u.kind != UserKind.STAFF or not _staff_visible(actor, u):
        raise not_found("Сотрудник")
    if u.id == actor.id and (body.role_ids is not None or body.branch_ids is not None or body.salary is not None
                             or body.is_active is not None):
        raise forbidden("Нельзя менять собственные роли, филиалы, оклад и статус")
    if u.id != actor.id:
        await _ensure_outranks(db, actor, u)
    if body.salary is not None and not actor.can("payroll", "adjust"):
        raise forbidden("Оклад меняет сотрудник с правом на зарплату")
    before = snapshot(u, ["full_name", "email", "position", "salary", "is_active"])
    before["roles"] = sorted(ur.role.code for ur in u.roles)
    if "owner" in before["roles"] and not actor.is_owner:
        raise forbidden("Супер-админа может менять только супер-админ")
    for f in ("full_name", "email", "position", "salary", "is_active"):
        v = getattr(body, f)
        if v is not None:
            setattr(u, f, v)
    if body.role_ids is not None or body.branch_ids is not None:
        role_ids = body.role_ids if body.role_ids is not None else [ur.role_id for ur in u.roles]
        branch_ids = body.branch_ids if body.branch_ids is not None else [b.branch_id for b in u.branches]
        roles = await _check_assignable(db, actor, role_ids, branch_ids)
        if "owner" in before["roles"] and "owner" not in {r.code for r in roles}:
            await _ensure_not_last_owner(db, u.id)
        for ur in list(u.roles):
            await db.delete(ur)
        for ub in list(u.branches):
            await db.delete(ub)
        await db.flush()
        for r in roles:
            db.add(UserRole(user_id=u.id, role_id=r.id))
        for b in set(branch_ids):
            db.add(UserBranch(user_id=u.id, branch_id=b))
        await revoke_all(db, u.id, "roles_changed")
    if body.is_active is False:
        if "owner" in before["roles"]:
            await _ensure_not_last_owner(db, u.id)
        await revoke_all(db, u.id, "deactivated")
    after = snapshot(u, ["full_name", "email", "position", "salary", "is_active"])
    after["roles"] = body.role_ids
    b, a = diff(before, after)
    await write_audit(db, actor_id=actor.id, action="staff.update", entity="user", entity_id=u.id, ip=actor.ip, before=b, after=a)
    await db.commit()
    u = await db.scalar(select(User).where(User.id == u.id).execution_options(populate_existing=True))
    return staff_out(u, actor)


async def _ensure_not_last_owner(db: DB, user_id: int) -> None:
    owners = (await db.scalars(
        select(UserRole.user_id).join(Role).join(User, User.id == UserRole.user_id)
        .where(Role.code == "owner", User.is_active.is_(True), User.archived_at.is_(None))
    )).all()
    if set(owners) <= {user_id}:
        raise forbidden("Нельзя снять последнего супер-админа")


@router.post("/staff/{user_id}/archive", status_code=204)
async def archive_staff(user_id: int, db: DB, actor: Actor = require("staff", "archive")) -> None:
    u = await db.get(User, user_id, populate_existing=True)
    if u is None or u.kind != UserKind.STAFF or not _staff_visible(actor, u):
        raise not_found("Сотрудник")
    if u.id == actor.id:
        raise forbidden("Нельзя архивировать себя")
    await _ensure_outranks(db, actor, u)
    if any(ur.role.code == "owner" for ur in u.roles):
        await _ensure_not_last_owner(db, u.id)
    u.archived_at = datetime.now(UTC)
    u.is_active = False
    await revoke_all(db, u.id, "archived")
    await write_audit(db, actor_id=actor.id, action="staff.archive", entity="user", entity_id=u.id, ip=actor.ip)
    await db.commit()


@router.post("/staff/{user_id}/reset-2fa", status_code=204)
async def reset_2fa(user_id: int, db: DB, actor: Actor = require("security", "manage")) -> None:
    if not actor.is_owner:
        raise forbidden("Сбросить 2FA может только супер-админ")
    u = await db.get(User, user_id, populate_existing=True)
    if u is None:
        raise not_found("Сотрудник")
    u.totp_enabled, u.totp_secret = False, None
    await revoke_all(db, u.id, "2fa_reset")
    await write_audit(db, actor_id=actor.id, action="security.2fa_reset", entity="user", entity_id=u.id, ip=actor.ip)
    await db.commit()


class PasswordSet(BaseModel):
    password: str


@router.post("/staff/{user_id}/password", status_code=204)
async def set_password(user_id: int, body: PasswordSet, db: DB, actor: Actor = require("staff", "edit")) -> None:
    u = await db.get(User, user_id, populate_existing=True)
    if u is None or u.kind != UserKind.STAFF or not _staff_visible(actor, u):
        raise not_found("Сотрудник")
    if any(ur.role.code == "owner" for ur in u.roles) and not actor.is_owner:
        raise forbidden()
    if u.id != actor.id:
        await _ensure_outranks(db, actor, u)
    if err := validate_password_strength(body.password):
        raise bad_request(err)
    u.password_hash = hash_password(body.password)
    await revoke_all(db, u.id, "password_reset")
    await write_audit(db, actor_id=actor.id, action="staff.password_reset", entity="user", entity_id=u.id, ip=actor.ip)
    await db.commit()


# ---------- security overview ----------
class StaffSessionOut(BaseModel):
    id: int
    user_id: int
    user_name: str
    user_agent: str | None
    ip: str | None
    last_used_at: datetime
    mfa_passed: bool


@router.get("/security/sessions", response_model=list[StaffSessionOut])
async def all_sessions(db: DB, actor: Actor = require("security", "view")) -> list[StaffSessionOut]:
    now = datetime.now(UTC)
    stmt = (select(AuthSession, User).join(User, User.id == AuthSession.user_id)
            .where(AuthSession.revoked_at.is_(None), AuthSession.expires_at > now, User.kind == UserKind.STAFF)
            .order_by(AuthSession.last_used_at.desc()).limit(500))
    allowed = actor.branches_for("security", "view")
    if allowed is not None:
        stmt = stmt.where(User.id.in_(select(UserBranch.user_id).where(UserBranch.branch_id.in_(allowed))))
    return [StaffSessionOut(id=s.id, user_id=u.id, user_name=u.full_name, user_agent=s.user_agent, ip=s.ip,
                            last_used_at=s.last_used_at, mfa_passed=s.mfa_passed) for s, u in (await db.execute(stmt)).all()]


@router.delete("/security/sessions/{session_id}", status_code=204)
async def kill_session(session_id: int, db: DB, actor: Actor = require("security", "manage")) -> None:
    s = await db.get(AuthSession, session_id)
    if s is None:
        raise not_found("Сессия")
    target = await db.get(User, s.user_id)
    allowed = actor.branches_for("security", "manage")
    if target is None or (allowed is not None and not ({b.branch_id for b in target.branches} & allowed)):
        raise not_found("Сессия")
    s.revoked_at, s.revoke_reason = datetime.now(UTC), f"ended_by:{actor.id}"
    await write_audit(db, actor_id=actor.id, action="security.session_ended", entity="session", entity_id=s.id,
                      ip=actor.ip, after={"user_id": s.user_id})
    await db.commit()


# ---------- audit ----------
class AuditOut(ORM):
    id: int
    at: datetime
    actor_id: int | None
    actor_name: str | None = None
    action: str
    entity: str
    entity_id: int | None
    branch_id: int | None
    before: dict
    after: dict
    ip: str | None
    note: str | None


@router.get("/audit", response_model=Page[AuditOut])
async def audit_log(
    db: DB, actor: Actor = require("audit", "view"), entity: str | None = None, entity_id: int | None = None,
    actor_id: int | None = None, action: str | None = None, since: datetime | None = None,
    limit: int = Query(50, le=200), offset: int = 0,
) -> Page[AuditOut]:
    stmt = select(AuditLog)
    allowed = actor.branches_for("audit", "view")
    if allowed is not None:
        stmt = stmt.where(AuditLog.branch_id.in_(allowed))
    conds = []
    if entity:
        conds.append(AuditLog.entity == entity)
    if entity_id:
        conds.append(AuditLog.entity_id == entity_id)
    if actor_id:
        conds.append(AuditLog.actor_id == actor_id)
    if action:
        conds.append(AuditLog.action.startswith(action))
    if since:
        conds.append(AuditLog.at >= since)
    if conds:
        stmt = stmt.where(and_(*conds))
    rows, total = await paginate(db, stmt.order_by(AuditLog.id.desc()), limit, offset)
    names = dict((await db.execute(select(User.id, User.full_name).where(User.id.in_({r.actor_id for r in rows if r.actor_id})))).all())
    items = []
    for r in rows:
        o = AuditOut.model_validate(r)
        o.actor_name = names.get(r.actor_id)
        items.append(o)
    return Page(items=items, total=total, limit=limit, offset=offset)


# ---------- settings & rates ----------
@router.get("/settings")
async def get_settings_(db: DB, actor: Actor = require("settings", "view")) -> dict:
    return {s.key: s.value.get("v") for s in await db.scalars(select(Setting))}


class SettingIn(BaseModel):
    value: bool | int | str | dict | list | None


@router.put("/settings/{key}", status_code=204)
async def put_setting(key: str, body: SettingIn, db: DB, actor: Actor = require("settings", "edit")) -> None:
    s = await db.scalar(select(Setting).where(Setting.key == key))
    if s is None:
        raise not_found("Настройка")
    before = s.value
    s.value, s.updated_by = {"v": body.value}, actor.id
    await write_audit(db, actor_id=actor.id, action="settings.update", entity="setting", entity_id=s.id, ip=actor.ip,
                      before=before, after=s.value, note=key)
    await db.commit()


class RateOut(ORM):
    key: str
    value: int
    effective_from: date


@router.get("/rates", response_model=list[RateOut])
async def list_rates(db: DB, actor: Actor = require("settings", "view")) -> list[RateOut]:
    return [RateOut.model_validate(r) for r in await db.scalars(select(RateSetting).order_by(RateSetting.key, RateSetting.effective_from))]


class RateIn(BaseModel):
    key: str
    value: int = Field(ge=0)
    effective_from: date


@router.post("/rates", response_model=RateOut, status_code=201)
async def add_rate(body: RateIn, db: DB, actor: Actor = require("settings", "edit")) -> RateOut:
    if not await db.scalar(select(RateSetting).where(RateSetting.key == body.key)):
        raise bad_request("Неизвестная ставка")
    if body.effective_from < datetime.now(UTC).date():
        raise bad_request("Новая ставка действует только с сегодняшнего дня или позже")
    if await db.scalar(select(RateSetting).where(RateSetting.key == body.key, RateSetting.effective_from == body.effective_from)):
        raise conflict("На эту дату ставка уже задана")
    r = RateSetting(key=body.key, value=body.value, effective_from=body.effective_from, created_by=actor.id)
    db.add(r)
    await write_audit(db, actor_id=actor.id, action="rates.add", entity="rate", ip=actor.ip,
                      after={"key": body.key, "value": body.value, "from": body.effective_from.isoformat()})
    await db.commit()
    return RateOut.model_validate(r)


__all__ = ["router", "NETWORK"]
