"""Instagram message ids are longer than 128 characters

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-17 11:40:00

Safe on the live database: two text columns only get a larger limit, no data is changed.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: Union[str, Sequence[str], None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("external_messages", "external_message_id", type_=sa.String(length=512), existing_nullable=True)
    op.alter_column("external_contacts", "external_id", type_=sa.String(length=255), existing_nullable=False)


def downgrade() -> None:
    op.alter_column("external_messages", "external_message_id", type_=sa.String(length=128), existing_nullable=True)
    op.alter_column("external_contacts", "external_id", type_=sa.String(length=128), existing_nullable=False)
