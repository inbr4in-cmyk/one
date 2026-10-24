"""Internal chats: group chats follow group membership; direct chats follow the who-may-message-whom rules.

Hard rules (DECISIONS.md №3) that no role setting can lift:
  * student ↔ student — never (only the shared group chat);
  * parent ↔ parent — never;
  * parent ↔ student — only the parent's own child.
Everything else is decided by the staff member's chats.* permissions and their data scope, symmetrically:
a student or parent may write to a staff member exactly when that staff member may write to them.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import NETWORK, OWN, Grants
from app.models import Chat, ChatMember, Group, GroupMember, Student, StudentGuardian, User
from app.models.identity import UserKind
from app.services.clock import now, today


async def grants_of(user: User) -> tuple[Grants, set[int]]:
    g = Grants()
    for ur in user.roles:
        if ur.role.archived_at is None:
            for p in ur.role.permissions:
                g.add(p.module, p.action, p.scope)
    return g, {b.branch_id for b in user.branches}


async def _students_of_user(db: AsyncSession, user: User) -> list[Student]:
    if user.kind == UserKind.STUDENT:
        return list(await db.scalars(select(Student).where(Student.user_id == user.id, Student.archived_at.is_(None))))
    if user.kind == UserKind.PARENT:
        return list(await db.scalars(
            select(Student).join(StudentGuardian, StudentGuardian.student_id == Student.id)
            .where(StudentGuardian.user_id == user.id, Student.archived_at.is_(None))
        ))
    return []


async def teaches(db: AsyncSession, teacher_id: int, student_ids: list[int]) -> bool:
    if not student_ids:
        return False
    row = await db.scalar(
        select(GroupMember.id).join(Group, Group.id == GroupMember.group_id)
        .where(Group.teacher_id == teacher_id, GroupMember.student_id.in_(student_ids), GroupMember.left_on.is_(None),
               Group.archived_at.is_(None)).limit(1)
    )
    return row is not None


async def staff_may_message(db: AsyncSession, staff: User, other: User) -> bool:
    grants, branches = await grants_of(staff)
    if other.kind == UserKind.STAFF:
        return grants.scope("chats", "message_staff") is not None
    action = "message_students" if other.kind == UserKind.STUDENT else "message_parents"
    scope = grants.scope("chats", action)
    if scope is None:
        return False
    if scope == NETWORK:
        return True
    students = await _students_of_user(db, other)
    if scope == OWN:
        return await teaches(db, staff.id, [s.id for s in students])
    return any(s.branch_id in branches for s in students)


async def direct_allowed(db: AsyncSession, a: User, b: User) -> tuple[bool, str]:
    if a.id == b.id:
        return False, "Нельзя написать самому себе"
    kinds = {a.kind, b.kind}
    if a.kind == b.kind == UserKind.STUDENT:
        return False, "Ученики не переписываются друг с другом лично — есть общий чат группы"
    if a.kind == b.kind == UserKind.PARENT:
        return False, "Родители не могут переписываться между собой"
    if kinds == {UserKind.STUDENT, UserKind.PARENT}:
        parent, student = (a, b) if a.kind == UserKind.PARENT else (b, a)
        own = await db.scalar(
            select(StudentGuardian.id).join(Student, Student.id == StudentGuardian.student_id)
            .where(StudentGuardian.user_id == parent.id, Student.user_id == student.id)
        )
        return (own is not None), ("" if own else "Родитель может писать только своему ребёнку")
    if a.kind == UserKind.STAFF and b.kind == UserKind.STAFF:
        ok = await staff_may_message(db, a, b)
        return ok, "" if ok else "Нет права писать сотрудникам"
    staff, other = (a, b) if a.kind == UserKind.STAFF else (b, a)
    if other is a:  # a student/parent starting the chat needs chats.message_staff too
        g, _ = await grants_of(a)
        if g.scope("chats", "message_staff") is None:
            return False, "Нет права писать сотрудникам"
    ok = await staff_may_message(db, staff, other)
    return ok, "" if ok else "Переписка с этим пользователем не разрешена"


def direct_key(a: int, b: int) -> str:
    x, y = sorted((a, b))
    return f"{x}:{y}"


async def add_member(db: AsyncSession, chat_id: int, user_id: int) -> None:
    m = await db.scalar(select(ChatMember).where(ChatMember.chat_id == chat_id, ChatMember.user_id == user_id))
    if m is None:
        db.add(ChatMember(chat_id=chat_id, user_id=user_id, joined_on=today()))
    elif m.left_on is not None:
        m.left_on = None
        m.joined_on = today()


async def remove_member(db: AsyncSession, chat_id: int, user_id: int) -> None:
    m = await db.scalar(select(ChatMember).where(ChatMember.chat_id == chat_id, ChatMember.user_id == user_id))
    if m is not None and m.left_on is None:
        m.left_on = today()


async def ensure_group_chat(db: AsyncSession, group: Group) -> Chat:
    """ТЗ 8: a group chat is created automatically for every group: teacher + students."""
    if group.chat_id:
        chat = await db.get(Chat, group.chat_id)
        if chat:
            return chat
    chat = Chat(kind="group", title=group.name, group_id=group.id, branch_id=group.branch_id, last_message_at=now())
    db.add(chat)
    await db.flush()
    group.chat_id = chat.id
    await add_member(db, chat.id, group.teacher_id)
    return chat


async def sync_student_in_group_chat(db: AsyncSession, group: Group, student: Student, present: bool) -> None:
    if not student.user_id:
        return
    chat = await ensure_group_chat(db, group)
    if present:
        await add_member(db, chat.id, student.user_id)
    else:
        await remove_member(db, chat.id, student.user_id)


async def change_group_teacher(db: AsyncSession, group: Group, old_teacher_id: int) -> None:
    chat = await ensure_group_chat(db, group)
    if old_teacher_id != group.teacher_id:
        await remove_member(db, chat.id, old_teacher_id)
        await add_member(db, chat.id, group.teacher_id)
