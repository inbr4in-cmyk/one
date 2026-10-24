from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

MAX_LIMIT = 200


async def paginate(db: AsyncSession, q: Select, limit: int, offset: int) -> tuple[list, int]:
    limit = max(1, min(limit, MAX_LIMIT))
    total = await db.scalar(select(func.count()).select_from(q.order_by(None).subquery()))
    rows = list((await db.scalars(q.limit(limit).offset(max(offset, 0)))).all())
    return rows, int(total or 0)
