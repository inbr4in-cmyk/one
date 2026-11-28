"""Import from the old CRM: source keys of imported rows, imported payments marked, staff without a phone

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-05 12:00:00

Safe on the live database, after 0002: one new table, one new nullable column, and users.phone becomes nullable
(existing rows keep their phones; the unique index stays). The owner role gets the new import.run right with network
scope, the same way the role builder would store it. Downgrade refuses to run while users without a phone exist.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: Union[str, Sequence[str], None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "import_refs",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("ext_key", sa.String(length=255), nullable=False),
        sa.Column("entity", sa.String(length=32), nullable=False),
        sa.Column("entity_id", sa.BigInteger(), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=True),
        sa.Column("meta", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("kind", "ext_key", name="import_refs_kind_key_uq"),
    )
    op.create_index("import_refs_entity_idx", "import_refs", ["entity", "entity_id"])
    op.add_column("payments", sa.Column("source", sa.String(length=16), nullable=True))
    op.alter_column("users", "phone", existing_type=sa.String(length=32), nullable=True)
    op.execute(
        "INSERT INTO role_permissions (role_id, module, action, scope) "
        "SELECT r.id, 'import', 'run', 'network' FROM roles r WHERE r.code = 'owner' "
        "AND NOT EXISTS (SELECT 1 FROM role_permissions p WHERE p.role_id = r.id AND p.module = 'import' AND p.action = 'run')"
    )


def downgrade() -> None:
    if op.get_bind().execute(sa.text("SELECT count(*) FROM users WHERE phone IS NULL")).scalar():
        raise RuntimeError("Users without a phone exist (imported staff): set their phones before downgrading")
    op.execute("DELETE FROM role_permissions WHERE module = 'import' AND action = 'run'")
    op.alter_column("users", "phone", existing_type=sa.String(length=32), nullable=False)
    op.drop_column("payments", "source")
    op.drop_index("import_refs_entity_idx", table_name="import_refs")
    op.drop_table("import_refs")
