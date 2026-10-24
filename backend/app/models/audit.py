from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin
from app.models._types import DT, IntN, Json, StrN


class AuditLog(IdMixin, Base):
    """Append-only. A DB trigger (see migration) rejects UPDATE and DELETE, even for the owner."""

    __tablename__ = "audit_log"

    at: Mapped[DT] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    actor_id: Mapped[IntN]
    action: Mapped[str] = mapped_column(String(64), index=True)
    entity: Mapped[str] = mapped_column(String(64), index=True)
    entity_id: Mapped[IntN]
    branch_id: Mapped[IntN]
    before: Mapped[Json]
    after: Mapped[Json]
    ip: Mapped[StrN]
    note: Mapped[StrN]
