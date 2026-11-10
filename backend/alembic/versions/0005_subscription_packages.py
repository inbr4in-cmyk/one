"""Subscription packages (абонементы)

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-10 13:00:00

Safe on the live database: one new table and two nullable columns on payments; nothing existing changes.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, Sequence[str], None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "subscription_packages",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("months", sa.Integer(), nullable=False),
        sa.Column("price", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("lessons", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("payments", sa.Column("package_id", sa.BigInteger(), sa.ForeignKey("subscription_packages.id", ondelete="RESTRICT"), nullable=True))
    op.create_index("ix_payments_package_id", "payments", ["package_id"])
    op.add_column("payments", sa.Column("valid_to", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("payments", "valid_to")
    op.drop_index("ix_payments_package_id", table_name="payments")
    op.drop_column("payments", "package_id")
    op.drop_table("subscription_packages")
