"""One rule for «access suspended until payment» (Правила; QA C-3).

A student whose lessons ran out and who hasn't paid within N days (jobs.block_nonpayers) loses the active parts
of the platform: homework, tests, schedule, chats (sending) and file upload, the coin shop.
Kept on purpose (DECISIONS.md №8): reading chats, balance and payments, rules and consents, complaints.
Parents are never blocked: they are the ones who pay, and they talk to the school about it.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import forbidden
from app.models import Student, User
from app.models.identity import UserKind

BLOCKED_MSG = "Доступ приостановлен до оплаты"


def is_blocked(student: Student) -> bool:
    return student.access_blocked_at is not None


async def user_blocked(db: AsyncSession, user: User) -> bool:
    """A student account is blocked when its (non-archived) student record is."""
    if user.kind != UserKind.STUDENT:
        return False
    return await db.scalar(select(Student.id).where(Student.user_id == user.id, Student.archived_at.is_(None),
                                                    Student.access_blocked_at.is_not(None)).limit(1)) is not None


async def ensure_user_access(db: AsyncSession, user: User) -> None:
    if await user_blocked(db, user):
        raise forbidden(BLOCKED_MSG)
