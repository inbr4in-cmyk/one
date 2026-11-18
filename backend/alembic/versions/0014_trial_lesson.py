"""Individual trial lesson created for a lead

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-18 18:00:00

Safe on the live database: one new column with a default, existing lessons get false.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: Union[str, Sequence[str], None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("lessons", sa.Column("is_trial", sa.Boolean(), nullable=False, server_default="false"))


def downgrade() -> None:
    op.drop_column("lessons", "is_trial")
