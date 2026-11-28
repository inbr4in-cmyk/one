"""Pre-release helper: regenerate the single initial migration from the models, keeping the hand-written SQL.

Only valid while there is no production database. After the first deploy, use normal incremental migrations.
"""

import glob
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXTRA_UP = '''
    # --- hand-written (scripts/regen_initial_migration.py) ---
    # ТЗ 1.4 + решение заказчика: журнал действий и леджеры неизменяемы, даже для владельца.
    op.execute("""
        CREATE OR REPLACE FUNCTION append_only() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION '% is append-only', TG_TABLE_NAME;
        END;
        $$ LANGUAGE plpgsql;
    """)
    for t in ("audit_log", "balance_entries", "coin_entries"):
        op.execute(f"CREATE TRIGGER {t}_no_change BEFORE UPDATE OR DELETE ON {t} FOR EACH ROW EXECUTE FUNCTION append_only();")
        op.execute(f"CREATE TRIGGER {t}_no_truncate BEFORE TRUNCATE ON {t} EXECUTE FUNCTION append_only();")
    # ТЗ 4.2: a room and a teacher can't hold two lessons at once — enforced by the database itself.
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.execute("""
        ALTER TABLE lessons ADD CONSTRAINT lessons_room_no_overlap
        EXCLUDE USING gist (room_id WITH =, tstzrange(starts_at, ends_at) WITH &&) WHERE (status <> 'cancelled')
    """)
    op.execute("""
        ALTER TABLE lessons ADD CONSTRAINT lessons_teacher_no_overlap
        EXCLUDE USING gist ((coalesce(actual_teacher_id, teacher_id)) WITH =, tstzrange(starts_at, ends_at) WITH &&)
        WHERE (status <> 'cancelled')
    """)
'''
EXTRA_DOWN = '''    op.execute("ALTER TABLE lessons DROP CONSTRAINT IF EXISTS lessons_room_no_overlap")
    op.execute("ALTER TABLE lessons DROP CONSTRAINT IF EXISTS lessons_teacher_no_overlap")
    for t in ("audit_log", "balance_entries", "coin_entries"):
        op.execute(f"DROP TRIGGER IF EXISTS {t}_no_change ON {t}")
        op.execute(f"DROP TRIGGER IF EXISTS {t}_no_truncate ON {t}")
    op.execute("DROP FUNCTION IF EXISTS append_only()")
'''


def main() -> None:
    env = {**os.environ}
    db = env.get("OE_DATABASE_URL", "postgresql+asyncpg://oe:oe@localhost:5432/one_english")
    psql = db.replace("+asyncpg", "")
    subprocess.run(["psql", "-q", "-o", "/dev/null", psql, "-c", "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"], check=True, stderr=subprocess.DEVNULL)
    for f in glob.glob(os.path.join(ROOT, "alembic/versions/*.py")):
        os.remove(f)
    subprocess.run(["alembic", "revision", "--autogenerate", "-m", "initial schema", "--rev-id", "0001"], cwd=ROOT, check=True,
                   capture_output=True)
    path = glob.glob(os.path.join(ROOT, "alembic/versions/0001_*.py"))[0]
    s = open(path).read()
    marker = "    # ### end Alembic commands ###\n"
    i = s.index(marker, s.index("def upgrade")) + len(marker)
    s = s[:i] + EXTRA_UP + s[i:]
    j = s.index("def downgrade() -> None:")
    k = s.index("\n", s.index('"""', j + 30)) + 1
    s = s[:k] + EXTRA_DOWN + s[k:]
    open(path, "w").write(s)
    subprocess.run(["alembic", "upgrade", "head"], cwd=ROOT, check=True, capture_output=True)
    print("ok:", os.path.basename(path))


if __name__ == "__main__":
    sys.exit(main())
