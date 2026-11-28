from sqlalchemy import BigInteger, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, TimestampMixin
from app.models._types import DTN, D, IntN, Money, StrN, fk


class RateSetting(IdMixin, TimestampMixin, Base):
    """Rates change from a date; past calculations keep the old value (ТЗ 10.1)."""

    __tablename__ = "rate_settings"
    __table_args__ = (UniqueConstraint("key", "effective_from"),)

    key: Mapped[str] = mapped_column(String(48))
    value: Mapped[Money]
    effective_from: Mapped[D]
    created_by: Mapped[IntN]


class Accrual(IdMixin, TimestampMixin, Base):
    __tablename__ = "accruals"
    # One fact can never produce the same bonus twice (ТЗ 10.5).
    __table_args__ = (UniqueConstraint("user_id", "kind", "ref_type", "ref_id"),)

    user_id: Mapped[int] = fk("users.id")
    branch_id: Mapped[int | None] = fk("branches.id", nullable=True)
    period: Mapped[str] = mapped_column(String(7), index=True)  # YYYY-MM
    # lesson | trial_retention | final_test | trial_visit | return | sale | salary | bonus | deduction | reversal
    kind: Mapped[str] = mapped_column(String(24))
    amount: Mapped[Money]  # negative for deductions/reversals
    ref_type: Mapped[StrN]
    ref_id: Mapped[IntN]
    description: Mapped[str] = mapped_column(String(255))
    created_by: Mapped[IntN]


class PayrollPeriod(IdMixin, TimestampMixin, Base):
    __tablename__ = "payroll_periods"
    __table_args__ = (UniqueConstraint("period", "branch_id"),)

    period: Mapped[str] = mapped_column(String(7))
    branch_id: Mapped[int] = fk("branches.id")
    status: Mapped[str] = mapped_column(String(16), default="draft")  # draft | approved | paid
    approved_by: Mapped[IntN]
    approved_at: Mapped[DTN]


class StaffDay(IdMixin, TimestampMixin, Base):
    """Табель: a staff member's day, marked by the branch admin. Salaried staff are paid for the days worked."""

    __tablename__ = "staff_days"
    __table_args__ = (UniqueConstraint("user_id", "day"),)

    user_id: Mapped[int] = fk("users.id")
    branch_id: Mapped[int] = fk("branches.id")
    day: Mapped[D]
    # work | off | sick | vacation | absent
    status: Mapped[str] = mapped_column(String(10))
    created_by: Mapped[IntN]


class StaffPayout(IdMixin, TimestampMixin, Base):
    """«Рассчитаться»: money actually handed to a staff member, one row per part of the pay. Rows of one payment
    share batch_id. A fine withheld at the payment is a negative row (part «deduction»)."""

    __tablename__ = "staff_payouts"

    user_id: Mapped[int] = fk("users.id")
    branch_id: Mapped[int] = fk("branches.id", index=False)
    period: Mapped[str] = mapped_column(String(7), index=True)
    batch_id: Mapped[int | None] = mapped_column(BigInteger, default=None, index=True)
    # salary | rate | kpi | bonus | deduction | carry (what is left from earlier months, or the debt)
    part: Mapped[str] = mapped_column(String(12))
    amount: Mapped[Money]
    paid_on: Mapped[D]
    note: Mapped[StrN]
    expense_id: Mapped[int | None] = fk("expenses.id", nullable=True, index=False)
    created_by: Mapped[IntN]
    cancelled_at: Mapped[DTN]
