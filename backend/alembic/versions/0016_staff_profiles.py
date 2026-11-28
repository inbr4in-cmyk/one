"""Staff profile (анкета): photo, education, experience, awards, about

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-19 11:30:00

Safe on the live database: one new empty table, no row is changed.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0016"
down_revision: Union[str, Sequence[str], None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "staff_profiles",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False, unique=True),
        sa.Column("photo_key", sa.String(length=255), nullable=True),
        sa.Column("about", sa.Text(), nullable=True),
        sa.Column("education", JSONB(), nullable=False, server_default="[]"),
        sa.Column("experience", JSONB(), nullable=False, server_default="[]"),
        sa.Column("awards", JSONB(), nullable=False, server_default="[]"),
        sa.Column("show_contacts", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_table("staff_profiles")
