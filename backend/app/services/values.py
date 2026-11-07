from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RateSetting, Setting
from app.seed import DEFAULT_SETTINGS, RATES


async def setting(db: AsyncSession, key: str) -> Any:
    s = await db.scalar(select(Setting).where(Setting.key == key))
    return s.value.get("v") if s else DEFAULT_SETTINGS.get(key)


async def rate(db: AsyncSession, key: str, on: date) -> int:
    """The rate in force on `on`: past facts keep the rate of their date (ТЗ 10.1)."""
    r = await db.scalar(
        select(RateSetting).where(RateSetting.key == key, RateSetting.effective_from <= on)
        .order_by(RateSetting.effective_from.desc()).limit(1)
    )
    return r.value if r else RATES[key]
