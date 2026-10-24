"""Platform rules acceptance, video/audio recording consent, complaints, notifications."""

from sqlalchemy import Boolean, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, TimestampMixin
from app.models._types import DT, DTN, Int, IntN, Json, StrN, TextN, fk


class DocumentVersion(IdMixin, TimestampMixin, Base):
    __tablename__ = "document_versions"
    __table_args__ = (UniqueConstraint("kind", "version"),)

    kind: Mapped[str] = mapped_column(String(16))  # rules | recording
    version: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(String(100_000))
    # Rule changes are announced at least 7 days before they apply.
    effective_from: Mapped[DT]


class Consent(IdMixin, Base):
    """Stores date, time and version of the accepted text (Правила: «Кто даёт согласие»)."""

    __tablename__ = "consents"

    user_id: Mapped[int] = fk("users.id")
    student_id: Mapped[int | None] = fk("students.id", nullable=True)  # parent signs for a child
    document_id: Mapped[int] = fk("document_versions.id")
    accepted_at: Mapped[DT]
    ip: Mapped[StrN]
    user_agent: Mapped[StrN]
    revoked_at: Mapped[DTN]


class Complaint(IdMixin, TimestampMixin, Base):
    """Правила «Порядок жалоб»: ack 24h, answer 3 business days (7 if a check is needed)."""

    __tablename__ = "complaints"

    author_id: Mapped[int] = fk("users.id")
    branch_id: Mapped[int | None] = fk("branches.id", nullable=True)
    subject: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(String(8000))
    # The person complained about never sees the complaint.
    against_user_id: Mapped[int | None] = fk("users.id", nullable=True)
    file_url: Mapped[StrN]
    # new | acknowledged | investigating | answered | appealed | closed
    status: Mapped[str] = mapped_column(String(16), default="new")
    acknowledged_at: Mapped[DTN]
    due_at: Mapped[DT]
    answer: Mapped[TextN]
    answered_by: Mapped[IntN]
    answered_at: Mapped[DTN]


class MessageTemplate(IdMixin, TimestampMixin, Base):
    __tablename__ = "message_templates"
    __table_args__ = (UniqueConstraint("code", "locale"),)

    # absence | payment | pay_reminder | lesson_cancel | lesson_move | book_sale | present | late
    code: Mapped[str] = mapped_column(String(32))
    locale: Mapped[str] = mapped_column(String(5), default="ru")
    body: Mapped[str] = mapped_column(String(2000))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # Name of the approved WhatsApp template on Meta's side (business-initiated messages).
    wa_template_name: Mapped[StrN]


class OutboundMessage(IdMixin, TimestampMixin, Base):
    """Delivery log of WhatsApp / push notifications with retries (ТЗ 7.2)."""

    __tablename__ = "outbound_messages"

    channel: Mapped[str] = mapped_column(String(16))  # whatsapp | push
    template_code: Mapped[StrN]
    to_user_id: Mapped[IntN]
    to_phone: Mapped[StrN]
    body: Mapped[str] = mapped_column(String(4000))
    variables: Mapped[Json]
    # queued | sent | delivered | read | failed
    status: Mapped[str] = mapped_column(String(16), default="queued")
    attempts: Mapped[Int]
    error: Mapped[StrN]
    external_id: Mapped[StrN]
    ref_type: Mapped[StrN]
    ref_id: Mapped[IntN]


class Notification(IdMixin, Base):
    """In-app notifications (bell)."""

    __tablename__ = "notifications"

    user_id: Mapped[int] = fk("users.id")
    at: Mapped[DT]
    kind: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[StrN]
    link: Mapped[StrN]
    read_at: Mapped[DTN]
    meta: Mapped[Json]


class Setting(IdMixin, TimestampMixin, Base):
    """Free-form admin settings: skip charge policy, reminder thresholds, coin amounts..."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), unique=True)
    value: Mapped[Json]
    updated_by: Mapped[IntN]
