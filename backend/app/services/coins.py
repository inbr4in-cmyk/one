from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CoinEntry
from app.services.clock import now
from app.services.values import setting


async def balance(db: AsyncSession, student_id: int) -> int:
    return int(await db.scalar(select(func.coalesce(func.sum(CoinEntry.delta), 0)).where(CoinEntry.student_id == student_id)))


async def award_auto(db: AsyncSession, student_id: int, kind: str, ref: tuple[str, int], reason: str) -> bool:
    amounts = await setting(db, "coins") or {}
    amount = int(amounts.get(kind, 0))
    if amount <= 0:
        return False
    stmt = (insert(CoinEntry).values(student_id=student_id, at=now(), kind=kind, delta=amount, reason=reason,
                                     ref_type=ref[0], ref_id=ref[1])
            .on_conflict_do_nothing(constraint="coin_entries_student_id_kind_ref_type_ref_id_key").returning(CoinEntry.id))
    return (await db.execute(stmt)).scalar() is not None
