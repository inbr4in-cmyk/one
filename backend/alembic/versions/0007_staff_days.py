"""Staff timesheet (табель); support lessons (no students, own teacher rate 1000)

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-12 14:00:00

Safe on the live database: one new table, one boolean column on lessons (false for all existing), one new rate.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, Sequence[str], None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "staff_days",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("branch_id", sa.BigInteger(), sa.ForeignKey("branches.id"), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "day"),
    )
    op.create_index("ix_staff_days_branch_day", "staff_days", ["branch_id", "day"])
    op.add_column("lessons", sa.Column("is_support", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.execute(
        "INSERT INTO rate_settings (key, value, effective_from) SELECT 'teacher_support_lesson', 1000, DATE '2026-11-01' "
        "WHERE NOT EXISTS (SELECT 1 FROM rate_settings WHERE key = 'teacher_support_lesson')"
    )


def downgrade() -> None:
    op.execute("DELETE FROM rate_settings WHERE key = 'teacher_support_lesson'")
    op.drop_column("lessons", "is_support")
    op.drop_index("ix_staff_days_branch_day", table_name="staff_days")
    op.drop_table("staff_days")
