"""Forms («анкеты»): a form with sections of questions and the answers people send

Revision ID: 0023
Revises: 0022
Create Date: 2026-11-25 12:30:00

Safe on the live database: two new empty tables, no row is changed.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0023"
down_revision: Union[str, Sequence[str], None] = "0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    ts = lambda: [  # noqa: E731
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]
    op.create_table(
        "forms",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        *ts(),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("code", sa.String(length=40), nullable=False, unique=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("thanks", sa.Text(), nullable=True),
        sa.Column("token", sa.String(length=40), nullable=False, unique=True),
        sa.Column("is_open", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sections", JSONB(), nullable=False, server_default="[]"),
    )
    op.create_table(
        "form_responses",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("form_id", sa.BigInteger(), sa.ForeignKey("forms.id"), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("branch_id", sa.BigInteger(), sa.ForeignKey("branches.id"), nullable=True),
        sa.Column("teacher_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=255), nullable=True),
        sa.Column("answers", JSONB(), nullable=False, server_default="{}"),
        sa.Column("flags", JSONB(), nullable=False, server_default="[]"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="new"),
        sa.Column("done_by", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("done_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
    )
    op.create_index("ix_form_responses_form_id", "form_responses", ["form_id"])
    op.create_index("ix_form_responses_branch_id", "form_responses", ["branch_id"])


def downgrade() -> None:
    op.drop_table("form_responses")
    op.drop_table("forms")
