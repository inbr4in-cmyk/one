"""A room can have its own fixed teacher pay per lesson

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-18 17:00:00

Safe on the live database: one new empty column, no row is changed.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: Union[str, Sequence[str], None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("rooms", sa.Column("teacher_rate", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("rooms", "teacher_rate")
