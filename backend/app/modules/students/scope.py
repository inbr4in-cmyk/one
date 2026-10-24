from sqlalchemy import or_, select, true

from app.core.deps import Actor
from app.core.errors import not_found
from app.core.permissions import NETWORK, OWN
from app.models import Group, GroupMember, Student


def taught_by(user_id: int):
    return (select(GroupMember.student_id).join(Group, Group.id == GroupMember.group_id)
            .where(Group.teacher_id == user_id, GroupMember.left_on.is_(None)))


def student_filter(actor: Actor, module: str = "students", action: str = "view"):
    """Data scope for student records: own = students I teach or brought/sold; branch = my branches; network = all."""
    scope = actor.scope(module, action)
    if scope == NETWORK:
        return true()
    if scope == OWN:
        return or_(Student.id.in_(taught_by(actor.id)), Student.sales_user_id == actor.id,
                   Student.office_user_id == actor.id)
    return Student.branch_id.in_(actor.branch_ids or {-1})


async def get_student_scoped(db, actor: Actor, student_id: int, module: str = "students", action: str = "view") -> Student:
    s = await db.scalar(select(Student).where(Student.id == student_id, student_filter(actor, module, action)))
    if s is None:
        # Same answer for "doesn't exist" and "not yours": no probing of other branches' ids.
        raise not_found("Ученик")
    return s
