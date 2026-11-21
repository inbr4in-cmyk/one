"""Rows brought in from another system (the school's old CRM). One row per imported source record."""

from sqlalchemy import BigInteger, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, TimestampMixin
from app.models._types import Json, StrN


class ImportRef(IdMixin, TimestampMixin, Base):
    """Source key → our record. Makes every import idempotent: the same source row never creates a second record.

    kind: what the source row was (student, teacher, group, payment, attendance, ...); ext_key: its key in the old system
    (client id, invoice number, normalised name, ...); fingerprint: hash of the source values, to tell «unchanged» from
    «changed» on a re-import; meta: values we need on the next run (e.g. the opening balance we applied)."""

    __tablename__ = "import_refs"
    __table_args__ = (
        UniqueConstraint("kind", "ext_key", name="import_refs_kind_key_uq"),
        Index("import_refs_entity_idx", "entity", "entity_id"),
    )

    kind: Mapped[str] = mapped_column(String(32))
    ext_key: Mapped[str] = mapped_column(String(255))
    entity: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[int] = mapped_column(BigInteger)
    fingerprint: Mapped[StrN] = mapped_column(String(64), default=None)
    meta: Mapped[Json]
