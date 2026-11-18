"""Who sees and who edits each funnel stage (table «сотрудник × этап»)

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-18 12:30:00

Safe on the live database: one new empty table. Until the admin fills it, everyone works as their role says.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: Union[str, Sequence[str], None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "lead_stage_access",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("stage_id", sa.BigInteger(), sa.ForeignKey("lead_stages.id"), nullable=False),
        sa.Column("level", sa.String(length=8), nullable=False),
        sa.UniqueConstraint("user_id", "stage_id"),
    )
    op.create_index("ix_lead_stage_access_user_id", "lead_stage_access", ["user_id"])
    op.create_index("ix_lead_stage_access_stage_id", "lead_stage_access", ["stage_id"])


def downgrade() -> None:
    op.drop_table("lead_stage_access")
