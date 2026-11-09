"""Course kinds (individual / duo / group), student contracts

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-09 12:00:00

Safe on the live database: two nullable columns and one column with a server default (existing groups stay «group»),
plus a partial unique index on the contract number of current (not archived) students.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, Sequence[str], None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("groups", sa.Column("kind", sa.String(length=16), nullable=False, server_default="group"))
    op.add_column("students", sa.Column("contract_no", sa.String(length=64), nullable=True))
    op.add_column("students", sa.Column("contract_date", sa.Date(), nullable=True))
    op.create_index("students_contract_no_uq", "students", ["contract_no"], unique=True,
                    postgresql_where=sa.text("archived_at IS NULL AND contract_no IS NOT NULL"))
    # Teacher pay for individual and duo lessons: a flat rate, same as the group base until the owner changes it.
    for key in ("teacher_individual_lesson", "teacher_duo_lesson"):
        op.execute(
            "INSERT INTO rate_settings (key, value, effective_from, created_at, updated_at) "
            f"SELECT '{key}', 2500, DATE '2020-01-01', now(), now() "
            f"WHERE NOT EXISTS (SELECT 1 FROM rate_settings WHERE key = '{key}')"
        )


def downgrade() -> None:
    op.execute("DELETE FROM rate_settings WHERE key IN ('teacher_individual_lesson', 'teacher_duo_lesson')")
    op.drop_index("students_contract_no_uq", table_name="students")
    op.drop_column("students", "contract_date")
    op.drop_column("students", "contract_no")
    op.drop_column("groups", "kind")
