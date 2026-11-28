"""Facebook / Instagram ads statistics by day and campaign (owner, 28.11.2026)

Revision ID: 0029
Revises: 0028

Safe on the live database: one new empty table.
"""
import sqlalchemy as sa
from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ad_insights",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("day", sa.Date, nullable=False),
        sa.Column("campaign_id", sa.String(64), nullable=False),
        sa.Column("campaign_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("currency", sa.String(8), nullable=False, server_default=""),
        sa.Column("spend", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("impressions", sa.Integer, nullable=False, server_default="0"),
        sa.Column("reach", sa.Integer, nullable=False, server_default="0"),
        sa.Column("clicks", sa.Integer, nullable=False, server_default="0"),
        sa.Column("link_clicks", sa.Integer, nullable=False, server_default="0"),
        sa.Column("results", sa.Integer, nullable=False, server_default="0"),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("day", "campaign_id"),
    )
    op.create_index("ix_ad_insights_day", "ad_insights", ["day"])


def downgrade() -> None:
    op.drop_table("ad_insights")
