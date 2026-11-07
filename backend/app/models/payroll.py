from sqlalchemy import String, UniqueConstraint
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
