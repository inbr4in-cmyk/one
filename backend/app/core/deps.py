from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_db
from app.core.errors import forbidden
from app.core.permissions import BRANCH, NETWORK, OWN, PORTAL_MODULES, Grants
from app.core.ratelimit import client_ip
from app.core.security import decode_access_token
from app.models.identity import AuthSession, User, UserKind

DB = Annotated[AsyncSession, Depends(get_db)]
_bearer = HTTPBearer(auto_error=False)


@dataclass
class Actor:
    user: User
    session_id: int
    mfa: bool
    ip: str
    grants: Grants = field(default_factory=Grants)
    branch_ids: set[int] = field(default_factory=set)
    role_codes: set[str] = field(default_factory=set)

    @property
    def id(self) -> int:
        return self.user.id

    @property
    def is_owner(self) -> bool:
        return "owner" in self.role_codes

    @property
    def is_staff(self) -> bool:
        return self.user.kind == UserKind.STAFF

    def can(self, module: str, action: str) -> bool:
        return self.grants.scope(module, action) is not None

    def scope(self, module: str, action: str) -> str:
        s = self.grants.scope(module, action)
        if s is None:
            raise forbidden()
        return s

    def branches_for(self, module: str, action: str) -> set[int] | None:
        """None means every branch (network scope)."""
        s = self.scope(module, action)
        return None if s == NETWORK else set(self.branch_ids)

    def ensure_branch(self, module: str, action: str, branch_id: int | None) -> None:
        allowed = self.branches_for(module, action)
        if allowed is not None and branch_id not in allowed:
            raise forbidden("Нет доступа к этому филиалу")

    def is_own_scope(self, module: str, action: str) -> bool:
        return self.scope(module, action) == OWN


async def load_actor(db: AsyncSession, user: User, session_id: int, mfa: bool, ip: str) -> Actor:
    actor = Actor(user=user, session_id=session_id, mfa=mfa, ip=ip)
    actor.branch_ids = {b.branch_id for b in user.branches}
    for ur in user.roles:
        role = ur.role
        if role.archived_at is not None:
            continue
        actor.role_codes.add(role.code)
        for p in role.permissions:
            actor.grants.add(p.module, p.action, p.scope)
    return actor


async def current_actor(
    request: Request,
    db: DB,
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Actor:
    unauthorized = HTTPException(status.HTTP_401_UNAUTHORIZED, "Требуется вход", headers={"WWW-Authenticate": "Bearer"})
    if creds is None:
        raise unauthorized
    try:
        data = decode_access_token(creds.credentials)
    except jwt.PyJWTError:
        raise unauthorized from None
    # The session must still be alive: logout / "end session" take effect immediately.
    sess = await db.get(AuthSession, int(data["sid"]))
    now = datetime.now(UTC)
    if sess is None or not sess.is_live(now) or sess.user_id != int(data["sub"]):
        raise unauthorized
    user = await db.scalar(select(User).where(User.id == sess.user_id))
    if user is None or not user.is_active or user.archived_at is not None:
        raise unauthorized
    actor = await load_actor(db, user, sess.id, bool(data.get("mfa")), client_ip(request))
    request.state.actor = actor
    return actor


CurrentActor = Annotated[Actor, Depends(current_actor)]


def require(module: str, action: str):
    """Route dependency: the actor must hold module.action (any scope)."""

    async def dep(actor: CurrentActor) -> Actor:
        if not actor.can(module, action):
            raise forbidden()
        # Portal accounts never reach staff modules, whatever a role says.
        if not actor.is_staff and module not in PORTAL_MODULES:
            raise forbidden()
        # Every staff action needs a 2FA session: money, contacts and exports are spread across many modules.
        if actor.is_staff and get_settings().require_staff_2fa and not actor.mfa:
            raise forbidden("Включите двухфакторную защиту, чтобы работать в системе")
        return actor

    return Depends(dep)


def require_staff():
    async def dep(actor: CurrentActor) -> Actor:
        if not actor.is_staff:
            raise forbidden()
        if get_settings().require_staff_2fa and not actor.mfa:
            raise forbidden("Включите двухфакторную защиту, чтобы работать в системе")
        return actor

    return Depends(dep)


__all__ = ["DB", "Actor", "CurrentActor", "require", "require_staff", "OWN", "BRANCH", "NETWORK"]
