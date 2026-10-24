from collections.abc import AsyncIterator
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.orm.decl_base import _declarative_constructor

from app.core.config import get_settings

engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    def __init__(self, **kwargs):
        # Apply scalar column defaults at construction time, so fresh objects are usable before flush.
        for col in self.__table__.columns:
            key = col.key
            if key in kwargs or col.default is None:
                continue
            if col.default.is_scalar:
                kwargs[key] = col.default.arg
            elif col.default.is_callable and col.type.__class__.__name__ == "JSONB":
                kwargs[key] = col.default.arg(None)
        _declarative_constructor(self, **kwargs)


class IdMixin:
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ArchiveMixin:
    """ТЗ 1.4: nothing is deleted physically, only archived."""

    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
