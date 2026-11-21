"""Lead work control: per-stage deadline, free leads, the seller of a payment; files for kinds of users

Revision ID: 0017
Revises: 0016
Create Date: 2026-11-21 14:40:00

Safe on the live database: new empty columns. Three stages get their deadline (trial booked 2 h after a no-show,
trial done 1 h, «Начнут позже» 3 h); leads standing in «Начнут позже» without a manager's note get 3 hours from
the moment of the update. No lead, payment or balance is changed otherwise. Two new empty tables: user_docs,
user_doc_accepts.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: Union[str, Sequence[str], None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("lead_stages", sa.Column("work_hours", sa.Integer(), nullable=True))
    op.add_column("leads", sa.Column("work_due_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("leads", sa.Column("free_since", sa.DateTime(timezone=True), nullable=True))
    op.add_column("payments", sa.Column("seller_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=True))
    op.create_table(
        "user_docs",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("audience", sa.String(length=72), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("file_key", sa.String(length=80), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("created_by", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_user_docs_audience", "user_docs", ["audience"])
    op.create_table(
        "user_doc_accepts",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("doc_id", sa.BigInteger(), sa.ForeignKey("user_docs.id"), nullable=False),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ip", sa.String(length=255), nullable=True),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.UniqueConstraint("doc_id", "user_id"),
    )
    op.execute("UPDATE lead_stages SET work_hours = 2 WHERE code = 'trial_booked'")
    op.execute("UPDATE lead_stages SET work_hours = 1 WHERE code = 'trial_done'")
    op.execute("UPDATE lead_stages SET work_hours = 3 WHERE name ILIKE 'Начн%' AND NOT is_won AND NOT is_lost")
    op.execute("""
        UPDATE leads l SET work_due_at = now() + interval '3 hours'
        FROM lead_stages s
        WHERE s.id = l.stage_id AND s.name ILIKE 'Начн%' AND NOT s.is_won AND NOT s.is_lost AND l.archived_at IS NULL
          AND NOT EXISTS (SELECT 1 FROM lead_events e WHERE e.lead_id = l.id AND e.kind IN ('note', 'call', 'meeting')
                          AND jsonb_exists(e.meta, 'result') AND e.at >= l.stage_changed_at)
    """)


def downgrade() -> None:
    op.drop_table("user_doc_accepts")
    op.drop_table("user_docs")
    op.drop_column("payments", "seller_id")
    op.drop_column("leads", "free_since")
    op.drop_column("leads", "work_due_at")
    op.drop_column("lead_stages", "work_hours")
