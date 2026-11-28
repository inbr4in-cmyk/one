"""Reason of a lead's refusal from a list (owner, 28.11.2026)

Revision ID: 0027
Revises: 0026

Safe on the live database: one new nullable column; leads that already stand on «Отказ» get «Другое» (the owner's
word), their text of the refusal is kept as it is.
"""
import sqlalchemy as sa
from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("leads", sa.Column("lost_kind", sa.String(16), nullable=True))
    op.execute("update leads set lost_kind = 'other' where lost_kind is null "
               "and stage_id in (select id from lead_stages where is_lost)")


def downgrade() -> None:
    op.drop_column("leads", "lost_kind")
