"""A lead from Instagram/WhatsApp has no branch until staff pick it

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-18 13:00:00

Safe on the live database: the column only stops being required, no row is changed.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: Union[str, Sequence[str], None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("leads", "branch_id", existing_type=sa.BigInteger(), nullable=True)


def downgrade() -> None:
    op.alter_column("leads", "branch_id", existing_type=sa.BigInteger(), nullable=False)
