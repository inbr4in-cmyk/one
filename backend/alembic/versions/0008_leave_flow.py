"""Leaving a course goes through the methodist; automatic follow-up tasks

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-14 13:00:00

Safe on the live database: new nullable columns, no data is changed. The «teacher can't hold two lessons at once»
rule now skips substituted lessons (a substitute may run their own lesson and the one they cover); every row that
passed the old rule passes the new one.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: Union[str, Sequence[str], None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("students", sa.Column("leave_requested_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("students", sa.Column("leave_requested_by", sa.Integer(), nullable=True))
    op.add_column("students", sa.Column("leave_reason", sa.String(length=500), nullable=True))
    op.add_column("students", sa.Column("return_note", sa.String(length=500), nullable=True))
    op.add_column("tasks", sa.Column("auto_kind", sa.String(length=16), nullable=True))
    op.execute("ALTER TABLE lessons DROP CONSTRAINT lessons_teacher_no_overlap")
    op.execute("""
        ALTER TABLE lessons ADD CONSTRAINT lessons_teacher_no_overlap
        EXCLUDE USING gist (teacher_id WITH =, tstzrange(starts_at, ends_at) WITH &&)
        WHERE (status <> 'cancelled' AND actual_teacher_id IS NULL)
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE lessons DROP CONSTRAINT lessons_teacher_no_overlap")
    op.execute("""
        ALTER TABLE lessons ADD CONSTRAINT lessons_teacher_no_overlap
        EXCLUDE USING gist ((coalesce(actual_teacher_id, teacher_id)) WITH =, tstzrange(starts_at, ends_at) WITH &&)
        WHERE (status <> 'cancelled')
    """)
    op.drop_column("tasks", "auto_kind")
    for c in ("return_note", "leave_reason", "leave_requested_by", "leave_requested_at"):
        op.drop_column("students", c)
