"""Lesson rating by QR: a link per lesson and the students' answers

Revision ID: 0018
Revises: 0017
Create Date: 2026-11-21 15:10:00

Safe on the live database: two new empty tables, no row is changed.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0018"
down_revision: Union[str, Sequence[str], None] = "0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "lesson_surveys",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("lesson_id", sa.BigInteger(), sa.ForeignKey("lessons.id"), nullable=False, unique=True),
        sa.Column("token", sa.String(length=40), nullable=False, unique=True),
        sa.Column("created_by", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("closes_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("questions", JSONB(), nullable=False, server_default="[]"),
    )
    op.create_table(
        "lesson_survey_answers",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("survey_id", sa.BigInteger(), sa.ForeignKey("lesson_surveys.id"), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("answers", JSONB(), nullable=False, server_default="[]"),
    )
    op.create_index("ix_lesson_survey_answers_survey_id", "lesson_survey_answers", ["survey_id"])


def downgrade() -> None:
    op.drop_table("lesson_survey_answers")
    op.drop_table("lesson_surveys")
