"""«Недозвон» in the «Возврат» funnel, right after «Ушёл» (owner, 27.11.2026)

Revision ID: 0026
Revises: 0025
"""
import sqlalchemy as sa
from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    c = op.get_bind()
    pid = c.execute(sa.text("select id from pipelines where code = 'return'")).scalar()
    if pid is None or c.execute(sa.text("select 1 from lead_stages where pipeline_id = :p and code = 'no_answer'"), {"p": pid}).scalar():
        return
    # The live site got the stage by hand on 27.11.2026 with a custom code: it only gets the standard code, nothing is added.
    mine = c.execute(sa.text("select id from lead_stages where pipeline_id = :p and archived_at is null and lower(name) = 'недозвон' "
                             "order by id limit 1"), {"p": pid}).scalar()
    if mine is not None:
        c.execute(sa.text("update lead_stages set code = 'no_answer' where id = :i"), {"i": mine})
        return
    after = c.execute(sa.text('select "order" from lead_stages where pipeline_id = :p and code = \'left\''), {"p": pid}).scalar()
    after = -1 if after is None else after
    c.execute(sa.text('update lead_stages set "order" = "order" + 1 where pipeline_id = :p and "order" > :o'), {"p": pid, "o": after})
    c.execute(sa.text(
        'insert into lead_stages (pipeline_id, name, code, "order", color, is_won, is_lost, stale_after_hours, created_at, updated_at) '
        "values (:p, 'Недозвон', 'no_answer', :o, '#C2410C', false, false, 72, now(), now())"), {"p": pid, "o": after + 1})


def downgrade() -> None:
    pass  # the stage may already hold cards: it stays
