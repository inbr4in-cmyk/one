"""QA round 2: payment idempotency key, one open lead per phone in a branch, missing cyclic foreign keys

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-04 12:00:00

Safe on the live database: adds a nullable column and two partial unique indexes. The leads index needs
no duplicate open leads with the same phone in a branch — the live database has no school data yet; if it
ever does, the upgrade stops with a clear error instead of guessing which lead to keep.
The three foreign keys declared with use_alter (students.lead_id, groups.chat_id, branches.admin_id) were never
created by 0001; they are added here.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, Sequence[str], None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FKS = [
    ("students_lead_id_fkey", "students", "lead_id", "leads"),
    ("groups_chat_id_fkey", "groups", "chat_id", "chats"),
    ("branches_admin_id_fkey", "branches", "admin_id", "users"),
]


def upgrade() -> None:
    op.add_column("payments", sa.Column("idempotency_key", sa.String(length=64), nullable=True))
    op.create_index("payments_idempotency_key_uq", "payments", ["idempotency_key"], unique=True,
                    postgresql_where=sa.text("idempotency_key IS NOT NULL"))
    dupes = op.get_bind().execute(sa.text(
        "SELECT branch_id, phone, count(*) FROM leads WHERE archived_at IS NULL AND student_id IS NULL AND phone IS NOT NULL "
        "GROUP BY branch_id, phone HAVING count(*) > 1 LIMIT 5")).all()
    if dupes:
        raise RuntimeError(f"Duplicate open leads by phone, merge or archive them first: {dupes}")
    op.create_index("leads_open_phone_uq", "leads", ["branch_id", "phone"], unique=True,
                    postgresql_where=sa.text("archived_at IS NULL AND student_id IS NULL AND phone IS NOT NULL"))
    for name, table, col, target in FKS:
        op.create_foreign_key(name, table, target, [col], ["id"], ondelete="RESTRICT")


def downgrade() -> None:
    for name, table, _, _ in FKS:
        op.drop_constraint(name, table, type_="foreignkey")
    op.drop_index("leads_open_phone_uq", table_name="leads")
    op.drop_index("payments_idempotency_key_uq", table_name="payments")
    op.drop_column("payments", "idempotency_key")
