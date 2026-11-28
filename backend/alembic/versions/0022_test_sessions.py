"""Group tests: a test of the level's bank planned for a group's lesson and taken by the students online

Revision ID: 0022
Revises: 0021
Create Date: 2026-11-25 13:00:00

Safe on the live database: one new empty table and new nullable columns on attempts, no row is changed.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0022"
down_revision: Union[str, Sequence[str], None] = "0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "test_sessions",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("test_id", sa.BigInteger, sa.ForeignKey("tests.id"), nullable=False, index=True),
        sa.Column("group_id", sa.BigInteger, sa.ForeignKey("groups.id"), nullable=False, index=True),
        sa.Column("lesson_id", sa.BigInteger, sa.ForeignKey("lessons.id"), nullable=True, index=True),
        sa.Column("branch_id", sa.BigInteger, sa.ForeignKey("branches.id"), nullable=False, index=True),
        sa.Column("time_limit_min", sa.Integer, nullable=False, server_default="60"),
        sa.Column("status", sa.String(16), nullable=False, server_default="planned"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.add_column("attempts", sa.Column("session_id", sa.BigInteger, sa.ForeignKey("test_sessions.id"), nullable=True))
    op.create_index("ix_attempts_session_id", "attempts", ["session_id"])
    op.add_column("attempts", sa.Column("q_order", JSONB, nullable=True))
    op.add_column("attempts", sa.Column("position", sa.Integer, nullable=False, server_default="0"))
    op.add_column("attempts", sa.Column("duration_sec", sa.Integer, nullable=True))
    op.add_column("attempts", sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("attempts", sa.Column("restores", sa.Integer, nullable=False, server_default="0"))


def downgrade() -> None:
    for c in ("restores", "voided_at", "duration_sec", "position", "q_order"):
        op.drop_column("attempts", c)
    op.drop_index("ix_attempts_session_id", "attempts")
    op.drop_column("attempts", "session_id")
    op.drop_table("test_sessions")
