"""Payouts to staff («Рассчитаться»): what was actually handed out, by part of the pay

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-19 10:30:00

Safe on the live database: one new empty table, no row is changed.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: Union[str, Sequence[str], None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "staff_payouts",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("branch_id", sa.BigInteger(), sa.ForeignKey("branches.id"), nullable=False),
        sa.Column("period", sa.String(length=7), nullable=False),
        sa.Column("batch_id", sa.BigInteger(), nullable=True),
        sa.Column("part", sa.String(length=12), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("paid_on", sa.Date(), nullable=False),
        sa.Column("note", sa.String(length=255), nullable=True),
        sa.Column("expense_id", sa.BigInteger(), sa.ForeignKey("expenses.id"), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_staff_payouts_user_id", "staff_payouts", ["user_id"])
    op.create_index("ix_staff_payouts_period", "staff_payouts", ["period"])
    op.create_index("ix_staff_payouts_batch_id", "staff_payouts", ["batch_id"])


def downgrade() -> None:
    op.drop_table("staff_payouts")
