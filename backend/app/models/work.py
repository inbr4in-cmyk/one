"""Tasks, staff check-ins and daily reports."""

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import ArchiveMixin, Base, IdMixin, TimestampMixin
from app.models._types import DT, DTN, IntN, StrN, TextN, fk


class TaskStatus:
    NEW = "new"
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    DONE = "done"
    CANCELLED = "cancelled"
    ALL = (NEW, IN_PROGRESS, REVIEW, DONE, CANCELLED)


class Task(IdMixin, TimestampMixin, ArchiveMixin, Base):
    __tablename__ = "tasks"

    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[TextN]
    creator_id: Mapped[int] = fk("users.id")
    branch_id: Mapped[int | None] = fk("branches.id", nullable=True)
    priority: Mapped[str] = mapped_column(String(8), default="normal")  # low | normal | high
    due_at: Mapped[DTN]
    status: Mapped[str] = mapped_column(String(16), default=TaskStatus.NEW)
    done_at: Mapped[DTN]
    # Optional link to a student / lead / group
    link_type: Mapped[StrN]
    link_id: Mapped[IntN]
    # daily | weekly — a template that spawns copies
    recurrence: Mapped[StrN]
    parent_task_id: Mapped[int | None] = fk("tasks.id", nullable=True)


class TaskAssignee(IdMixin, Base):
    __tablename__ = "task_assignees"
    __table_args__ = (UniqueConstraint("task_id", "user_id"),)

    task_id: Mapped[int] = fk("tasks.id")
    user_id: Mapped[int] = fk("users.id")


class TaskComment(IdMixin, Base):
    __tablename__ = "task_comments"

    task_id: Mapped[int] = fk("tasks.id")
    author_id: Mapped[int] = fk("users.id")
    at: Mapped[DT]
    text: Mapped[str] = mapped_column(String(4000))
    file_url: Mapped[StrN]


class StaffCheckin(IdMixin, Base):
    """Правила: приход и уход сотрудников отмечаются на платформе."""

    __tablename__ = "staff_checkins"

    user_id: Mapped[int] = fk("users.id")
    branch_id: Mapped[int] = fk("branches.id")
    in_at: Mapped[DT]
    out_at: Mapped[DTN]


class DailyReport(IdMixin, TimestampMixin, Base):
    __tablename__ = "daily_reports"
    __table_args__ = (UniqueConstraint("user_id", "day"),)

    user_id: Mapped[int] = fk("users.id")
    day: Mapped[str] = mapped_column(String(10))
    text: Mapped[str] = mapped_column(String(8000))
