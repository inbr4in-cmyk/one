"""«Работать как»: a staff member with several roles may pick one to work in

Revision ID: 0020
Revises: 0019
Create Date: 2026-11-23 13:40:00

Safe on the live database: one new nullable column, no row is changed.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0020"
down_revision: Union[str, Sequence[str], None] = "0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("active_role", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "active_role")
