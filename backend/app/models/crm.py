from decimal import Decimal

from sqlalchemy import Boolean, Index, Integer, Numeric, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import ArchiveMixin, Base, IdMixin, TimestampMixin
from app.models._types import DT, DTN, D, Int, IntN, Json, StrN, TextN, fk


class LeadSource:
    SALES = "sales"  # cold calls, invitations
    QR = "qr"  # placement test via QR
    SITE = "site"
    INSTAGRAM = "instagram"
    WHATSAPP = "whatsapp"
    REFERRAL = "referral"
    RETURN = "return"  # former student back in the «Возврат» funnel
    WALK_IN = "walk_in"  # came to the reception
    IMPORT = "import"
    ALL = (SALES, QR, SITE, INSTAGRAM, WHATSAPP, REFERRAL, RETURN, WALK_IN, IMPORT)


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
    # Owner's rule 21.11.2026: hours the responsible manager has to work a lead on this stage (a note, a call, a
    # trial booking, a reply). After that the lead is «свободный»: everyone sees it, who works it first takes it.
    # On «Записан на пробный» the clock starts when the client did not come to the trial. Empty = no control.
    work_hours: Mapped[IntN]


class LeadStageAccess(IdMixin, Base):
    """The admin's table «сотрудник × этап воронки»: a row narrows what the person's role gives on that stage.
    No row = as the role says. level: none (the stage and its leads are hidden) | view (read only) |
    own (only the leads the person owns or is responsible for)."""

    __tablename__ = "lead_stage_access"
    __table_args__ = (UniqueConstraint("user_id", "stage_id"),)

    user_id: Mapped[int] = fk("users.id")
    stage_id: Mapped[int] = fk("lead_stages.id")
    level: Mapped[str] = mapped_column(String(8))


class Lead(IdMixin, TimestampMixin, ArchiveMixin, Base):
    __tablename__ = "leads"
    # QA H-15: one open lead per phone in a branch, even under parallel requests. A lead stops counting once it is
    # archived or became a student (the «Возврат» funnel then opens a new card for the same phone).
    __table_args__ = (
        Index("leads_open_phone_uq", "branch_id", "phone", unique=True,
              postgresql_where=text("archived_at IS NULL AND student_id IS NULL AND phone IS NOT NULL")),
    )

    full_name: Mapped[str] = mapped_column(String(255))
    phone: Mapped[StrN] = mapped_column(String(32), index=True, default=None)
    age: Mapped[IntN]
    parent_name: Mapped[StrN]
    parent_phone: Mapped[StrN]
    # Empty for a lead that wrote to Instagram/WhatsApp until staff pick the branch (on contact or trial booking).
    branch_id: Mapped[int | None] = fk("branches.id", nullable=True)
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
    lost_reason: Mapped[StrN]  # the manager's own words about the refusal
    # Why the lead refused (owner, 28.11.2026): online | other_city | far | other. Needed for the conversion numbers.
    lost_kind: Mapped[str | None] = mapped_column(String(16), default=None)
    next_action_at: Mapped[DTN]
    last_activity_at: Mapped[DTN]
    notes: Mapped[TextN]
    is_hot: Mapped[bool] = mapped_column(Boolean, default=False)
    work_due_at: Mapped[DTN]  # the responsible manager must work the lead before this moment
    free_since: Mapped[DTN]  # he did not: the lead is open to every manager until somebody works it


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
    external_id: Mapped[str] = mapped_column(String(255))  # IG-scoped id or wa_id
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
    # WhatsApp: which of the school's numbers the client wrote to — the branch id of that number; empty = the first
    # (main) number. The answer leaves from the same number.
    wa_line: Mapped[int | None] = mapped_column(Integer, nullable=True)


class ExternalMessage(IdMixin, Base):
    __tablename__ = "external_messages"

    conversation_id: Mapped[int] = fk("conversations.id")
    at: Mapped[DT]
    direction: Mapped[str] = mapped_column(String(4))  # in | out
    external_message_id: Mapped[StrN] = mapped_column(String(512), unique=True, default=None)
    kind: Mapped[str] = mapped_column(String(16), default="text")  # text | image | audio | file | story_reply | template
    text: Mapped[TextN]
    media_url: Mapped[StrN]
    # queued | sent | delivered | read | failed | received
    status: Mapped[str] = mapped_column(String(16), default="received")
    error: Mapped[StrN]
    sender_id: Mapped[IntN]


class AdInsight(IdMixin, Base):
    """Facebook / Instagram ads statistics of one campaign for one day, read from Meta (owner, 28.11.2026).
    Money is in the ad account's currency, with cents: it is Meta's number, not our tenge ledger."""

    __tablename__ = "ad_insights"
    __table_args__ = (UniqueConstraint("day", "campaign_id"),)

    day: Mapped[D]
    campaign_id: Mapped[str] = mapped_column(String(64))
    campaign_name: Mapped[str] = mapped_column(String(255), default="")
    currency: Mapped[str] = mapped_column(String(8), default="")
    spend: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    impressions: Mapped[Int]
    reach: Mapped[Int]
    clicks: Mapped[Int]
    link_clicks: Mapped[Int]
    results: Mapped[Int]  # leads and conversations started, as Meta counts them
    synced_at: Mapped[DT]
