from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

MAX_LIMIT = 200


async def paginate(db: AsyncSession, q: Select, limit: int, offset: int) -> tuple[list, int]:
    limit = max(1, min(limit, MAX_LIMIT))
    total = await db.scalar(select(func.count()).select_from(q.order_by(None).subquery()))
    rows = list((await db.scalars(q.limit(limit).offset(max(offset, 0)))).all())
    return rows, int(total or 0)


def like_escape(text: str) -> str:
    """Escape LIKE wildcards so «%», «_» and «\\» in a search box match literally (QA H-13)."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def icontains(column, text: str):
    """Case-insensitive substring match with the user's text taken literally."""
    return column.ilike(f"%{like_escape(text.strip())}%", escape="\\")


def contains_digits(column, digits: str):
    return column.like(f"%{like_escape(digits)}%", escape="\\")
