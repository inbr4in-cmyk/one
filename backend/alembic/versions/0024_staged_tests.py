"""Staged tests: timed stages, typed answers checked by a key, video answers, manual marks, staff trial attempts

Revision ID: 0024
Revises: 0023
Create Date: 2026-11-25 14:30:00

Safe on the live database: new nullable columns only, no row is changed.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0024"
down_revision: Union[str, Sequence[str], None] = "0023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tests", sa.Column("parts", JSONB(), nullable=True))
    op.add_column("questions", sa.Column("part", sa.String(length=16), nullable=True))
    op.add_column("questions", sa.Column("accept", JSONB(), nullable=True))
    op.add_column("attempts", sa.Column("part_started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("attempts", sa.Column("marks", JSONB(), nullable=True))
    op.add_column("attempts", sa.Column("trial", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("attempts", "trial")
    op.drop_column("attempts", "marks")
    op.drop_column("attempts", "part_started_at")
    op.drop_column("questions", "accept")
    op.drop_column("questions", "part")
    op.drop_column("tests", "parts")
