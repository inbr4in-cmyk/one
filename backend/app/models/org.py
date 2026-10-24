from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import ArchiveMixin, Base, IdMixin, TimestampMixin
from app.models._types import Int, Money, StrN, fk


class Branch(IdMixin, TimestampMixin, ArchiveMixin, Base):
    __tablename__ = "branches"

    name: Mapped[str] = mapped_column(String(120))
    address: Mapped[StrN]
    phone: Mapped[StrN]
    hours: Mapped[StrN]
    admin_id: Mapped[int | None] = fk("users.id", nullable=True, use_alter=True)


class Room(IdMixin, TimestampMixin, ArchiveMixin, Base):
    __tablename__ = "rooms"

    branch_id: Mapped[int] = fk("branches.id")
    name: Mapped[str] = mapped_column(String(64))
    capacity: Mapped[Int]
    equipment: Mapped[StrN]
    # active | repair
    status: Mapped[str] = mapped_column(String(16), default="active")


class Level(IdMixin, TimestampMixin, ArchiveMixin, Base):
    __tablename__ = "levels"

    name: Mapped[str] = mapped_column(String(80))
    code: Mapped[str] = mapped_column(String(32), unique=True)
    color: Mapped[str] = mapped_column(String(16), default="#1A6FD1")
    lesson_price: Mapped[Money]
    order: Mapped[Int]
    track: Mapped[str] = mapped_column(String(16), default="adults")  # adults | kids | exam
    duration_months: Mapped[Int]
    next_level_id: Mapped[int | None] = fk("levels.id", nullable=True)
    is_kids: Mapped[bool] = mapped_column(Boolean, default=False)
