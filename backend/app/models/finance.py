from sqlalchemy import Boolean, String
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
