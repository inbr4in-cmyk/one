"""Lesson plan of a level: what is taught lesson by lesson; a held lesson remembers its plan item

Revision ID: 0021
Revises: 0020
Create Date: 2026-11-25 12:00:00

Safe on the live database: one new empty table and one new nullable column, no row is changed.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: Union[str, Sequence[str], None] = "0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "level_plan_items",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("level_id", sa.Integer, sa.ForeignKey("levels.id"), nullable=False, index=True),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("month", sa.Integer, nullable=False, server_default="1"),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False, server_default="lesson"),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.add_column("lessons", sa.Column("plan_item_id", sa.Integer, sa.ForeignKey("level_plan_items.id"), nullable=True))


def downgrade() -> None:
    op.drop_column("lessons", "plan_item_id")
    op.drop_table("level_plan_items")
