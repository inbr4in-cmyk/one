"""A WhatsApp number per branch: the chat remembers which of the school's numbers the client wrote to

Revision ID: 0025
Revises: 0024
Create Date: 2026-11-27 17:00:00

Safe on the live database: one new nullable column, no row is changed.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0025"
down_revision: Union[str, Sequence[str], None] = "0024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("conversations", sa.Column("wa_line", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("conversations", "wa_line")
