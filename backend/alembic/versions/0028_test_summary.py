"""Group test: when the summary went to the methodist (owner, 28.11.2026)

Revision ID: 0028
Revises: 0027

Safe on the live database: one new nullable column. Tests finished before this release get no late summary.
"""
import sqlalchemy as sa
from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("test_sessions", sa.Column("summary_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("update test_sessions set summary_at = finished_at where status = 'finished'")


def downgrade() -> None:
    op.drop_column("test_sessions", "summary_at")
