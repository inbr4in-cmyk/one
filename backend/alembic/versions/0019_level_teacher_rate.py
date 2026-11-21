"""Teacher pay per lesson set on the course (level): IELTS pays 5000 in any format

Revision ID: 0019
Revises: 0018
Create Date: 2026-11-21 17:30:00

Safe on the live database: one new nullable column. The IELTS levels get 5000 (owner's rule of 21.11.2026);
pay already accrued for held lessons is not recalculated here.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: Union[str, Sequence[str], None] = "0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("levels", sa.Column("teacher_rate", sa.Integer(), nullable=True))
    op.execute("UPDATE levels SET teacher_rate = 5000 WHERE code ILIKE 'IELTS%' OR name ILIKE '%IELTS%'")


def downgrade() -> None:
    op.drop_column("levels", "teacher_rate")
