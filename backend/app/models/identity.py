from datetime import datetime

from sqlalchemy import Boolean, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import ArchiveMixin, Base, IdMixin, TimestampMixin
from app.models._types import DTN, DT, Int, Money, StrN, fk


class UserKind:
    STAFF = "staff"
    STUDENT = "student"
    PARENT = "parent"


class User(IdMixin, TimestampMixin, ArchiveMixin, Base):
    __tablename__ = "users"

    kind: Mapped[str] = mapped_column(String(16), index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    # NULL only for staff imported from the old CRM without a phone: they cannot sign in until the owner sets one.
    phone: Mapped[str | None] = mapped_column(String(32), unique=True, index=True, nullable=True)
    email: Mapped[StrN]
    password_hash: Mapped[StrN]
    totp_secret: Mapped[StrN]
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    locale: Mapped[str] = mapped_column(String(5), default="ru")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    avatar_url: Mapped[StrN]
    position: Mapped[StrN]
    salary: Mapped[Money]  # monthly base salary for staff, tenge
    # rates — paid by rates only (lessons, sales…); salary — fixed monthly salary only; both — salary + rates
    pay_scheme: Mapped[str] = mapped_column(String(8), default="rates", server_default="rates")
    last_login_at: Mapped[DTN]
    failed_logins: Mapped[Int]
    locked_until: Mapped[DTN]
    # Rules (Правила платформы): access opens only after accepting the rules.
    rules_accepted_version: Mapped[StrN]

    roles: Mapped[list["UserRole"]] = relationship(back_populates="user", lazy="selectin")
    branches: Mapped[list["UserBranch"]] = relationship(lazy="selectin")


class Role(IdMixin, TimestampMixin, ArchiveMixin, Base):
    __tablename__ = "roles"

    name: Mapped[str] = mapped_column(String(120))
    code: Mapped[str] = mapped_column(String(64), unique=True)
    description: Mapped[StrN]
    # System roles (owner, student, parent) cannot be archived (ТЗ 2.1).
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    # Monthly limit of coins a holder can award manually (teachers, ТЗ 14.1).
    coin_limit: Mapped[Int]

    permissions: Mapped[list["RolePermission"]] = relationship(
        back_populates="role", lazy="selectin", cascade="all, delete-orphan"
    )


class RolePermission(IdMixin, Base):
    __tablename__ = "role_permissions"
    __table_args__ = (UniqueConstraint("role_id", "module", "action"),)

    role_id: Mapped[int] = fk("roles.id", ondelete="CASCADE")
    module: Mapped[str] = mapped_column(String(48))
    action: Mapped[str] = mapped_column(String(48))
    # own | branch | network
    scope: Mapped[str] = mapped_column(String(16), default="branch")

    role: Mapped[Role] = relationship(back_populates="permissions")


class UserRole(IdMixin, Base):
    __tablename__ = "user_roles"
    __table_args__ = (UniqueConstraint("user_id", "role_id"),)

    user_id: Mapped[int] = fk("users.id", ondelete="CASCADE")
    role_id: Mapped[int] = fk("roles.id")

    user: Mapped[User] = relationship(back_populates="roles")
    role: Mapped[Role] = relationship(lazy="selectin")


class UserBranch(IdMixin, Base):
    __tablename__ = "user_branches"
    __table_args__ = (UniqueConstraint("user_id", "branch_id"),)

    user_id: Mapped[int] = fk("users.id", ondelete="CASCADE")
    branch_id: Mapped[int] = fk("branches.id")


class AuthSession(IdMixin, Base):
    """One row per device login. Refresh tokens rotate; reuse of an old token kills the family."""

    __tablename__ = "auth_sessions"

    user_id: Mapped[int] = fk("users.id", ondelete="CASCADE")
    refresh_hash: Mapped[str] = mapped_column(String(64), unique=True)
    prev_refresh_hash: Mapped[StrN]
    user_agent: Mapped[StrN]
    ip: Mapped[StrN]
    mfa_passed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[DT]
    last_used_at: Mapped[DT]
    expires_at: Mapped[DT]
    revoked_at: Mapped[DTN]
    revoke_reason: Mapped[StrN]

    def is_live(self, now: datetime) -> bool:
        return self.revoked_at is None and self.expires_at > now
