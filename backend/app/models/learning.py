

from sqlalchemy import BigInteger, Boolean, Index, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import ArchiveMixin, Base, IdMixin, TimestampMixin
from app.models._types import DT, DTN, D, DateN, Int, IntN, Money, StrN, TextN, TimeT, fk


class StudentStatus:
    LEAD = "lead"
    TRIAL = "trial"
    ACTIVE = "active"
    FROZEN = "frozen"
    FINISHED = "finished"
    LEFT = "left"
    ALL = (LEAD, TRIAL, ACTIVE, FROZEN, FINISHED, LEFT)


class Student(IdMixin, TimestampMixin, ArchiveMixin, Base):
    __tablename__ = "students"
    __table_args__ = (
        Index("students_contract_no_uq", "contract_no", unique=True,
              postgresql_where=text("archived_at IS NULL AND contract_no IS NOT NULL")),
    )

    user_id: Mapped[int | None] = fk("users.id", nullable=True)
    full_name: Mapped[str] = mapped_column(String(255), index=True)
    birth_date: Mapped[DateN]
    phone: Mapped[StrN] = mapped_column(String(32), index=True, default=None)
    photo_url: Mapped[StrN]
    branch_id: Mapped[int] = fk("branches.id")
    level_id: Mapped[int | None] = fk("levels.id", nullable=True)
    status: Mapped[str] = mapped_column(String(16), default=StudentStatus.ACTIVE, index=True)
    source: Mapped[StrN]
    sales_user_id: Mapped[int | None] = fk("users.id", nullable=True)
    office_user_id: Mapped[int | None] = fk("users.id", nullable=True)
    lead_id: Mapped[int | None] = fk("leads.id", nullable=True, use_alter=True)
    # Cached balance; the source of truth is balance_entries.
    lessons_paid: Mapped[Int]
    lessons_done: Mapped[Int]
    lessons_left: Mapped[Int]
    money_balance: Mapped[Money]
    # Price per lesson of the lessons currently on the balance (price at payment time, ТЗ 5.2).
    balance_lesson_price: Mapped[Money]
    access_blocked_at: Mapped[DTN]
    last_payment_at: Mapped[DTN]
    last_visit_at: Mapped[DTN]
    left_at: Mapped[DTN]
    stars: Mapped[Int]  # kids' stars for following the rules
    notes: Mapped[TextN]
    contract_no: Mapped[StrN] = mapped_column(String(64), default=None)
    contract_date: Mapped[DateN]


class StudentGuardian(IdMixin, Base):
    __tablename__ = "student_guardians"
    __table_args__ = (UniqueConstraint("student_id", "user_id"),)

    student_id: Mapped[int] = fk("students.id")
    user_id: Mapped[int] = fk("users.id")
    relation: Mapped[StrN]  # мама, папа, ...
    whatsapp: Mapped[StrN]
    notify: Mapped[bool] = mapped_column(Boolean, default=True)


class BalanceEntry(IdMixin, Base):
    """Ledger of lesson/money balance changes. Never updated, only appended."""

    __tablename__ = "balance_entries"

    student_id: Mapped[int] = fk("students.id")
    at: Mapped[DT]
    # payment | lesson | transfer | refund | freeze | manual | trial
    kind: Mapped[str] = mapped_column(String(24))
    lessons_delta: Mapped[Int]
    money_delta: Mapped[Money]
    lesson_price: Mapped[Money]
    lessons_after: Mapped[Int]
    money_after: Mapped[Money]
    ref_type: Mapped[StrN]
    ref_id: Mapped[IntN]
    actor_id: Mapped[IntN]
    note: Mapped[StrN]


class Group(IdMixin, TimestampMixin, ArchiveMixin, Base):
    __tablename__ = "groups"

    name: Mapped[str] = mapped_column(String(120))
    branch_id: Mapped[int] = fk("branches.id")
    level_id: Mapped[int | None] = fk("levels.id", nullable=True)  # empty for an open lesson (kind «club»)
    teacher_id: Mapped[int] = fk("users.id")
    room_id: Mapped[int | None] = fk("rooms.id", nullable=True)
    capacity: Mapped[int] = mapped_column(default=12)
    starts_on: Mapped[DateN]
    # recruiting | active | finished
    status: Mapped[str] = mapped_column(String(16), default="active")
    # group | duo (2 students) | individual (1 student): icon and filter in the schedule, teacher pay rate
    kind: Mapped[str] = mapped_column(String(16), default="group", server_default="group")
    chat_id: Mapped[int | None] = fk("chats.id", nullable=True, use_alter=True)


class GroupMember(IdMixin, Base):
    __tablename__ = "group_members"

    group_id: Mapped[int] = fk("groups.id")
    student_id: Mapped[int] = fk("students.id")
    joined_on: Mapped[D]
    left_on: Mapped[DateN]


class ScheduleRule(IdMixin, TimestampMixin, ArchiveMixin, Base):
    """Regular schedule, e.g. Mon/Wed/Fri 16:00–17:30 (ТЗ 4.2)."""

    __tablename__ = "schedule_rules"

    group_id: Mapped[int] = fk("groups.id")
    weekdays: Mapped[list[int]] = mapped_column(ARRAY(BigInteger))  # 0=Mon … 6=Sun
    start_time: Mapped[TimeT]
    end_time: Mapped[TimeT]
    room_id: Mapped[int] = fk("rooms.id")
    teacher_id: Mapped[int] = fk("users.id")
    valid_from: Mapped[D]
    valid_to: Mapped[DateN]


class LessonStatus:
    PLANNED = "planned"
    DONE = "done"
    CANCELLED = "cancelled"


class Lesson(IdMixin, TimestampMixin, Base):
    __tablename__ = "lessons"

    branch_id: Mapped[int] = fk("branches.id")
    group_id: Mapped[int | None] = fk("groups.id", nullable=True)
    student_id: Mapped[int | None] = fk("students.id", nullable=True)  # individual lesson
    level_id: Mapped[int | None] = fk("levels.id", nullable=True)
    teacher_id: Mapped[int] = fk("users.id")
    # Substitute teacher: pay goes to whoever actually taught (ТЗ 4.2).
    actual_teacher_id: Mapped[int | None] = fk("users.id", nullable=True)
    room_id: Mapped[int] = fk("rooms.id")
    rule_id: Mapped[int | None] = fk("schedule_rules.id", nullable=True)
    starts_at: Mapped[DT] = mapped_column(index=True)
    ends_at: Mapped[DT]
    status: Mapped[str] = mapped_column(String(16), default=LessonStatus.PLANNED)
    cancel_reason: Mapped[StrN]
    moved_from_id: Mapped[int | None] = fk("lessons.id", nullable=True)
    attendance_marked_at: Mapped[DTN]
    topic: Mapped[StrN]
    # Support lesson: a one-off lesson of a teacher without students (manager sets time, room, teacher, topic)
    is_support: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


class AttendanceStatus:
    PRESENT = "present"
    ABSENT = "absent"
    LATE = "late"
    EXCUSED = "excused"
    ALL = (PRESENT, ABSENT, LATE, EXCUSED)


class Attendance(IdMixin, TimestampMixin, Base):
    __tablename__ = "attendance"
    __table_args__ = (UniqueConstraint("lesson_id", "student_id"), UniqueConstraint("lesson_id", "lead_id"))

    lesson_id: Mapped[int] = fk("lessons.id")
    student_id: Mapped[int | None] = fk("students.id", nullable=True)
    lead_id: Mapped[int | None] = fk("leads.id", nullable=True)  # trial visitor
    status: Mapped[str] = mapped_column(String(16))
    charged: Mapped[bool] = mapped_column(Boolean, default=False)
    grade: Mapped[IntN]
    comment: Mapped[StrN]
    stars: Mapped[Int]
    marked_by: Mapped[int] = fk("users.id")


class Homework(IdMixin, TimestampMixin, ArchiveMixin, Base):
    __tablename__ = "homework"

    group_id: Mapped[int] = fk("groups.id")
    lesson_id: Mapped[int | None] = fk("lessons.id", nullable=True)
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[TextN]
    due_at: Mapped[DTN]
    created_by: Mapped[int] = fk("users.id")


class HomeworkSubmission(IdMixin, TimestampMixin, Base):
    __tablename__ = "homework_submissions"
    __table_args__ = (UniqueConstraint("homework_id", "student_id"),)

    homework_id: Mapped[int] = fk("homework.id")
    student_id: Mapped[int] = fk("students.id")
    # assigned | submitted | checked
    status: Mapped[str] = mapped_column(String(16), default="submitted")
    file_url: Mapped[StrN]
    answer: Mapped[TextN]
    grade: Mapped[IntN]
    teacher_comment: Mapped[StrN]


class Freeze(IdMixin, TimestampMixin, Base):
    __tablename__ = "freezes"

    student_id: Mapped[int] = fk("students.id")
    starts_on: Mapped[D]
    ends_on: Mapped[D]
    reason: Mapped[StrN]
    created_by: Mapped[int] = fk("users.id")
    ended_early_on: Mapped[DateN]


class Transfer(IdMixin, Base):
    __tablename__ = "transfers"

    student_id: Mapped[int] = fk("students.id")
    at: Mapped[DT]
    from_group_id: Mapped[int | None] = fk("groups.id", nullable=True)
    to_group_id: Mapped[int] = fk("groups.id")
    from_level_id: Mapped[int | None] = fk("levels.id", nullable=True)
    to_level_id: Mapped[int] = fk("levels.id")
    lessons_before: Mapped[Int]
    money_before: Mapped[Money]
    lessons_after: Mapped[Int]
    money_after: Mapped[Money]
    actor_id: Mapped[int] = fk("users.id")
    reason: Mapped[StrN]




class LessonRating(IdMixin, TimestampMixin, Base):
    """Student/parent rates a held lesson (ТЗ 16.6 «Оценка урока»). Only admins see the comments."""

    __tablename__ = "lesson_ratings"
    __table_args__ = (UniqueConstraint("lesson_id", "student_id"),)

    lesson_id: Mapped[int] = fk("lessons.id")
    student_id: Mapped[int] = fk("students.id")
    user_id: Mapped[int] = fk("users.id")
    stars: Mapped[int]
    comment: Mapped[StrN]
