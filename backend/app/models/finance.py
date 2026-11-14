from datetime import date

from sqlalchemy import Boolean, Date, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import ArchiveMixin, Base, IdMixin, TimestampMixin
from app.models._types import DT, D, Int, IntN, Money, StrN, fk


class PaymentMethod:
    CASH = "cash"
    CARD = "card"
    KASPI = "kaspi"
    TRANSFER = "transfer"
    ONLINE = "online"
    ALL = (CASH, CARD, KASPI, TRANSFER, ONLINE)


class Payment(IdMixin, TimestampMixin, Base):
    __tablename__ = "payments"

    student_id: Mapped[int] = fk("students.id")
    branch_id: Mapped[int] = fk("branches.id")
    level_id: Mapped[int | None] = fk("levels.id", nullable=True)
    # course | book | shop
    category: Mapped[str] = mapped_column(String(16), default="course")
    amount: Mapped[Money]  # actually paid
    discount: Mapped[Money]
    promo_code: Mapped[StrN]
    lessons: Mapped[Int]
    lesson_price: Mapped[Money]
    method: Mapped[str] = mapped_column(String(16))
    received_by: Mapped[int] = fk("users.id")
    paid_at: Mapped[DT]
    refunded: Mapped[Money]
    # First paid course payment after a trial = "sale" (KPI for office manager).
    is_first: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[StrN]
    # Idempotency-Key of the request that created it: a retried request returns this payment (QA C-1).
    idempotency_key: Mapped[str | None] = mapped_column(String(64), default=None)
    # "import" = brought in from the old CRM: history only, no balance change, no bonuses/KPI, no messages.
    source: Mapped[str | None] = mapped_column(String(16), default=None)
    # Subscription (абонемент) sale: the package and the last day it covers.
    package_id: Mapped[int | None] = fk("subscription_packages.id", nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date, default=None)

    __table_args__ = (
        Index("payments_idempotency_key_uq", "idempotency_key", unique=True, postgresql_where=text("idempotency_key IS NOT NULL")),
    )


class SubscriptionPackage(IdMixin, TimestampMixin, ArchiveMixin, Base):
    """Абонемент: N months for a fixed price; sold as a payment that adds `lessons` to the balance."""

    __tablename__ = "subscription_packages"

    name: Mapped[str] = mapped_column(String(120))
    months: Mapped[int] = mapped_column(Integer)
    price: Mapped[Money]
    lessons: Mapped[int] = mapped_column(Integer)


class Refund(IdMixin, TimestampMixin, Base):
    __tablename__ = "refunds"

    payment_id: Mapped[int] = fk("payments.id")
    amount: Mapped[Money]
    lessons_removed: Mapped[Int]
    reason: Mapped[str] = mapped_column(String(255))
    created_by: Mapped[int] = fk("users.id")


class ExpenseCategory(IdMixin, TimestampMixin, ArchiveMixin, Base):
    __tablename__ = "expense_categories"

    name: Mapped[str] = mapped_column(String(120))
    code: Mapped[str] = mapped_column(String(32), unique=True)


class Expense(IdMixin, TimestampMixin, ArchiveMixin, Base):
    __tablename__ = "expenses"

    # NULL branch = shared network expense, distributed between branches in reports.
    branch_id: Mapped[int | None] = fk("branches.id", nullable=True)
    category_id: Mapped[int] = fk("expense_categories.id")
    amount: Mapped[Money]
    spent_on: Mapped[D]
    note: Mapped[StrN]
    receipt_url: Mapped[StrN]
    recurring: Mapped[bool] = mapped_column(Boolean, default=False)
    recurring_day: Mapped[IntN]
    source_ref: Mapped[StrN]  # e.g. "payroll:2026-10:3" or "book_in:12" (auto expenses)
    created_by: Mapped[IntN]
