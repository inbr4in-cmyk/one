"""Students of a support lesson (a make-up lesson for a few picked students)

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-18 17:30:00

Safe on the live database: one new empty table, no row is changed.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: Union[str, Sequence[str], None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "lesson_students",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("lesson_id", sa.BigInteger(), sa.ForeignKey("lessons.id"), nullable=False),
        sa.Column("student_id", sa.BigInteger(), sa.ForeignKey("students.id"), nullable=False),
        sa.UniqueConstraint("lesson_id", "student_id"),
    )
    op.create_index("ix_lesson_students_lesson_id", "lesson_students", ["lesson_id"])
    op.create_index("ix_lesson_students_student_id", "lesson_students", ["student_id"])


def downgrade() -> None:
    op.drop_table("lesson_students")
