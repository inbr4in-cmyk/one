"""One-off, by the owner's written request of 21.11: students with the status «Закончил» (brought from the old CRM)
go to the archive, so they do not show in the working lists. They stay visible under Ученики → статус «Архив» and
can be restored there. Students with lessons or money on the balance, or still in a group, are skipped and listed.

    python 2026-11-21-archive-finished.py            preview, changes nothing
    python 2026-11-21-archive-finished.py commit     apply
"""
import asyncio
import sys

from sqlalchemy import select

from app.core.audit import write_audit
from app.core.db import SessionLocal
from app.models import GroupMember, Student, User
from app.models.identity import UserKind
from app.modules.auth.service import revoke_all
from app.models.learning import StudentStatus
from app.services.clock import now

COMMIT = len(sys.argv) > 1 and sys.argv[1] == "commit"


async def main():
    async with SessionLocal() as db:
        rows = list(await db.scalars(select(Student).where(Student.status == StudentStatus.FINISHED,
                                                           Student.archived_at.is_(None)).order_by(Student.id)))
        in_group = set((await db.scalars(select(GroupMember.student_id).where(GroupMember.left_on.is_(None)))).all())
        skip = [s for s in rows if s.lessons_left or s.money_balance or s.id in in_group]
        todo = [s for s in rows if s not in skip]
        print(f"finished, not archived: {len(rows)}; to archive: {len(todo)}; skipped: {len(skip)}")
        for s in skip:
            print(f"  skip {s.id} {s.full_name}: lessons {s.lessons_left}, money {s.money_balance}, in group {s.id in in_group}")
        print(f"  with a portal account among those to archive: {sum(1 for s in todo if s.user_id)}")
        if COMMIT:
            at = now()
            for s in todo:
                s.archived_at = at
                portal = await db.get(User, s.user_id) if s.user_id else None
                if portal is not None and portal.kind == UserKind.STUDENT:
                    await revoke_all(db, portal.id, "archived")  # the student's own account signs out
                await write_audit(db, actor_id=None, action="student.archive", entity="student", entity_id=s.id,
                                  branch_id=s.branch_id, ip=None, note="По просьбе владельца 21.11: «Закончил» из старой CRM в архив")
            await db.commit()
        print("\ncommitted" if COMMIT else "\npreview only, nothing changed")


asyncio.run(main())
