"""Placement test (QR), final level tests (150 points) and staff training tests."""

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import ArchiveMixin, Base, IdMixin, TimestampMixin
from app.models._types import DT, DTN, Int, IntN, Json, StrN, TextN, fk


class Test(IdMixin, TimestampMixin, ArchiveMixin, Base):
    __tablename__ = "tests"
    __test__ = False  # not a pytest class

    kind: Mapped[str] = mapped_column(String(16))  # placement | progress | final | training
    title: Mapped[str] = mapped_column(String(255))
    level_id: Mapped[int | None] = fk("levels.id", nullable=True)
    max_score: Mapped[int] = mapped_column(default=150)
    pass_score: Mapped[IntN]
    time_limit_min: Mapped[IntN]
    # placement: [{"min": 0, "level_id": 1}, {"min": 20, "level_id": 2}, ...]
    scale: Mapped[Json]
    is_published: Mapped[bool] = mapped_column(Boolean, default=False)
    # A test made of timed stages (owner, 25.11.2026): [{"id", "section", "title", "hint", "minutes", "text", "audio",
    # "words", "seconds"}]. Every stage is one page with its own time; no way back to a finished stage.
    parts: Mapped[list | None] = mapped_column(JSONB, nullable=True, default=None)


class Question(IdMixin, TimestampMixin, ArchiveMixin, Base):
    __tablename__ = "questions"

    test_id: Mapped[int] = fk("tests.id")
    order: Mapped[Int]
    # single | multi | input (a typed answer checked against `accept`) | text (manual) | video (speaking, manual)
    kind: Mapped[str] = mapped_column(String(16), default="single")
    part: Mapped[str | None] = mapped_column(String(16), nullable=True, default=None)  # the stage of Test.parts it belongs to
    accept: Mapped[list | None] = mapped_column(JSONB, nullable=True, default=None)  # input: the answers counted as right
    text: Mapped[str] = mapped_column(String(2000))
    options: Mapped[Json]  # ["a", "b", ...]
    correct: Mapped[Json]  # [index, ...]; never sent to test takers
    points: Mapped[int] = mapped_column(default=1)


class Attempt(IdMixin, TimestampMixin, Base):
    __tablename__ = "attempts"

    test_id: Mapped[int] = fk("tests.id")
    student_id: Mapped[int | None] = fk("students.id", nullable=True)
    lead_id: Mapped[int | None] = fk("leads.id", nullable=True)
    user_id: Mapped[int | None] = fk("users.id", nullable=True)
    branch_id: Mapped[int | None] = fk("branches.id", nullable=True)
    taker_name: Mapped[StrN]
    taker_phone: Mapped[StrN]
    answers: Mapped[Json]
    auto_score: Mapped[Int]
    manual_score: Mapped[IntN]
    score: Mapped[Int]
    # in_progress | needs_review | done
    status: Mapped[str] = mapped_column(String(16), default="in_progress")
    recommended_level_id: Mapped[int | None] = fk("levels.id", nullable=True)
    started_at: Mapped[DT]
    finished_at: Mapped[DTN]
    reviewed_by: Mapped[IntN]
    # a group test taken online: the student's own order of questions, where he is, how long it took
    session_id: Mapped[int | None] = fk("test_sessions.id", nullable=True)
    q_order: Mapped[list | None] = mapped_column(JSONB, nullable=True, default=None)
    position: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    duration_sec: Mapped[IntN]
    voided_at: Mapped[DTN]  # left the test page: annulled until the teacher restores it
    restores: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    part_started_at: Mapped[DTN]  # a staged test: when the current stage began for this person
    marks: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=None)  # manual points: {question id: points}
    trial: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")  # staff trying the test themselves


class TestSession(IdMixin, TimestampMixin, Base):
    """A test of the bank planned for a group's lesson. planned → running (the teacher starts it, timer) → finished."""
    __tablename__ = "test_sessions"
    __test__ = False

    test_id: Mapped[int] = fk("tests.id")
    group_id: Mapped[int] = fk("groups.id")
    lesson_id: Mapped[int | None] = fk("lessons.id", nullable=True)
    branch_id: Mapped[int] = fk("branches.id")
    time_limit_min: Mapped[int] = mapped_column(Integer, default=60, server_default="60")
    status: Mapped[str] = mapped_column(String(16), default="planned", server_default="planned")
    started_at: Mapped[DTN]
    ends_at: Mapped[DTN]
    finished_at: Mapped[DTN]
    created_by: Mapped[IntN]


class Course(IdMixin, TimestampMixin, ArchiveMixin, Base):
    """Staff training base (ТЗ 15)."""

    __tablename__ = "training_courses"

    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[TextN]
    role_codes: Mapped[Json]  # ["teacher", "office_manager"]


class Material(IdMixin, TimestampMixin, ArchiveMixin, Base):
    __tablename__ = "training_materials"

    course_id: Mapped[int] = fk("training_courses.id")
    order: Mapped[Int]
    kind: Mapped[str] = mapped_column(String(16))  # video | document | test
    title: Mapped[str] = mapped_column(String(255))
    url: Mapped[StrN]
    body: Mapped[TextN]
    test_id: Mapped[int | None] = fk("tests.id", nullable=True)


class MaterialProgress(IdMixin, Base):
    __tablename__ = "training_progress"

    user_id: Mapped[int] = fk("users.id")
    material_id: Mapped[int] = fk("training_materials.id")
    done_at: Mapped[DT]
    score: Mapped[IntN]


class Form(IdMixin, TimestampMixin, ArchiveMixin, Base):
    """An «анкета» (owner, 25.11.2026): sections of questions with branching, filled by a link. Open: anyone with the
    link, no account. Closed: signed-in users only. The answers are kept like applications and seen by admins only."""

    __tablename__ = "forms"

    code: Mapped[str] = mapped_column(String(40), unique=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[TextN]
    thanks: Mapped[TextN]
    token: Mapped[str] = mapped_column(String(40), unique=True)
    is_open: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # [{"id", "title", "text", "next", "questions": [{"id", "text", "kind", "required", "options": [{"text", "goto", "alert"}], ...}]}]
    sections: Mapped[list] = mapped_column(JSONB, default=list)


class FormResponse(IdMixin, Base):
    __tablename__ = "form_responses"

    form_id: Mapped[int] = fk("forms.id")
    at: Mapped[DT]
    branch_id: Mapped[int | None] = fk("branches.id", nullable=True)
    teacher_id: Mapped[int | None] = fk("users.id", nullable=True, index=False)
    user_id: Mapped[int | None] = fk("users.id", nullable=True, index=False)  # who filled it, when signed in
    name: Mapped[StrN]
    phone: Mapped[StrN]
    answers: Mapped[dict] = mapped_column(JSONB, default=dict)  # {question id: value}
    flags: Mapped[list] = mapped_column(JSONB, default=list)  # why the admin should call today
    status: Mapped[str] = mapped_column(String(16), default="new")  # new | done
    done_by: Mapped[int | None] = fk("users.id", nullable=True, index=False)
    done_at: Mapped[DTN]
    note: Mapped[TextN]
