"""Staff pay scheme: by rates, fixed monthly salary (оклад), or both

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-11 16:00:00

Safe on the live database: one column with a default; staff who already have a salary get «both», so nothing they
earn by rates today changes.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, Sequence[str], None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("pay_scheme", sa.String(length=8), nullable=False, server_default="rates"))
    op.execute("UPDATE users SET pay_scheme = 'both' WHERE kind = 'staff' AND salary > 0")


def downgrade() -> None:
    op.drop_column("users", "pay_scheme")
