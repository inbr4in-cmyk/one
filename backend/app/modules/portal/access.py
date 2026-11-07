from sqlalchemy import select

from app.core.deps import DB, Actor
from app.core.errors import forbidden, not_found
from app.models import Student, StudentGuardian
from app.models.identity import UserKind
from app.services.access import BLOCKED_MSG, is_blocked


async def my_students(db: DB, actor: Actor) -> list[Student]:
    """A student account sees itself; a parent sees every child linked to them."""
    if actor.user.kind == UserKind.STUDENT:
        q = select(Student).where(Student.user_id == actor.id)
    elif actor.user.kind == UserKind.PARENT:
        q = select(Student).join(StudentGuardian, StudentGuardian.student_id == Student.id).where(StudentGuardian.user_id == actor.id)
    else:
        return []
    return list(await db.scalars(q.where(Student.archived_at.is_(None)).order_by(Student.full_name)))


async def portal_student(db: DB, actor: Actor, student_id: int, allow_blocked: bool = False) -> Student:
    """The student behind a portal request; staff never act through the portal."""
    s = next((x for x in await my_students(db, actor) if x.id == student_id), None)
    if s is None:
        raise not_found("Ученик")
    if is_blocked(s) and not allow_blocked:
        raise forbidden(BLOCKED_MSG)
    return s
