from sqlalchemy import Boolean, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import ArchiveMixin, Base, IdMixin, TimestampMixin
from app.models._types import DT, DTN, Int, IntN, Json, StrN, TextN, fk


class LeadSource:
    SALES = "sales"  # cold calls, invitations
    QR = "qr"  # placement test via QR
    SITE = "site"
    INSTAGRAM = "instagram"
    WHATSAPP = "whatsapp"
    REFERRAL = "referral"
    RETURN = "return"  # former student back in the «Возврат» funnel
    ALL = (SALES, QR, SITE, INSTAGRAM, WHATSAPP, REFERRAL, RETURN)


class Pipeline(IdMixin, TimestampMixin, ArchiveMixin, Base):
    __tablename__ = "pipelines"

    name: Mapped[str] = mapped_column(String(120))
    code: Mapped[str] = mapped_column(String(32), unique=True)  # main | return


class LeadStage(IdMixin, TimestampMixin, ArchiveMixin, Base):
    __tablename__ = "lead_stages"

    pipeline_id: Mapped[int] = fk("pipelines.id")
    name: Mapped[str] = mapped_column(String(120))
    # new | contacted | trial_booked | trial_done | paid | lost (custom stages have custom codes)
    code: Mapped[str] = mapped_column(String(32))
    order: Mapped[Int]
    color: Mapped[str] = mapped_column(String(16), default="#5B6782")
    is_won: Mapped[bool] = mapped_column(Boolean, default=False)
    is_lost: Mapped[bool] = mapped_column(Boolean, default=False)
    # A lead sitting longer than this is «зависший» (ТЗ 9.2).
    stale_after_hours: Mapped[IntN]


class Lead(IdMixin, TimestampMixin, ArchiveMixin, Base):
    __tablename__ = "leads"

    full_name: Mapped[str] = mapped_column(String(255))
    phone: Mapped[StrN] = mapped_column(String(32), index=True, default=None)
    age: Mapped[IntN]
    parent_name: Mapped[StrN]
    parent_phone: Mapped[StrN]
    branch_id: Mapped[int] = fk("branches.id")
    pipeline_id: Mapped[int] = fk("pipelines.id")
    stage_id: Mapped[int] = fk("lead_stages.id")
    stage_changed_at: Mapped[DT]
    source: Mapped[str] = mapped_column(String(16))
    # Who attracted the lead: basis for sales KPI (ТЗ 9.1).
    owner_id: Mapped[int | None] = fk("users.id", nullable=True)
    assignee_id: Mapped[int | None] = fk("users.id", nullable=True)
    student_id: Mapped[int | None] = fk("students.id", nullable=True)
    level_id: Mapped[int | None] = fk("levels.id", nullable=True)
    placement_score: Mapped[IntN]
    trial_lesson_id: Mapped[int | None] = fk("lessons.id", nullable=True)
    lost_reason: Mapped[StrN]
    next_action_at: Mapped[DTN]
    last_activity_at: Mapped[DTN]
    notes: Mapped[TextN]
    is_hot: Mapped[bool] = mapped_column(Boolean, default=False)


class LeadEvent(IdMixin, Base):
    __tablename__ = "lead_events"

    lead_id: Mapped[int] = fk("leads.id")
    at: Mapped[DT]
    # created | stage | call | note | message | test | trial | sale | lost | merge
    kind: Mapped[str] = mapped_column(String(24))
    text: Mapped[TextN]
    actor_id: Mapped[IntN]
    meta: Mapped[Json]


class ExternalContact(IdMixin, TimestampMixin, Base):
    """A person writing to us from Instagram Direct or WhatsApp."""

    __tablename__ = "external_contacts"
    __table_args__ = (UniqueConstraint("channel", "external_id"),)

    channel: Mapped[str] = mapped_column(String(16))  # instagram | whatsapp
    external_id: Mapped[str] = mapped_column(String(128))  # IG-scoped id or wa_id
    display_name: Mapped[StrN]
    username: Mapped[StrN]
    phone: Mapped[StrN]
    lead_id: Mapped[int | None] = fk("leads.id", nullable=True)
    student_id: Mapped[int | None] = fk("students.id", nullable=True)


class Conversation(IdMixin, TimestampMixin, Base):
    __tablename__ = "conversations"

    contact_id: Mapped[int] = fk("external_contacts.id")
    channel: Mapped[str] = mapped_column(String(16))
    branch_id: Mapped[int | None] = fk("branches.id", nullable=True)
    assignee_id: Mapped[int | None] = fk("users.id", nullable=True)
    unread: Mapped[Int]
    last_message_at: Mapped[DTN]
    last_inbound_at: Mapped[DTN]  # 24h customer-care window for free-form replies
    last_preview: Mapped[StrN]
    status: Mapped[str] = mapped_column(String(16), default="open")  # open | closed


class ExternalMessage(IdMixin, Base):
    __tablename__ = "external_messages"

    conversation_id: Mapped[int] = fk("conversations.id")
    at: Mapped[DT]
    direction: Mapped[str] = mapped_column(String(4))  # in | out
    external_message_id: Mapped[StrN] = mapped_column(String(128), unique=True, default=None)
    kind: Mapped[str] = mapped_column(String(16), default="text")  # text | image | audio | file | story_reply | template
    text: Mapped[TextN]
    media_url: Mapped[StrN]
    # queued | sent | delivered | read | failed | received
    status: Mapped[str] = mapped_column(String(16), default="received")
    error: Mapped[StrN]
    sender_id: Mapped[IntN]
