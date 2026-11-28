from datetime import date, datetime
from typing import Any

from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog

# Never written to the audit log in clear text.
_SECRET_FIELDS = {"password_hash", "totp_secret", "refresh_hash", "prev_refresh_hash"}


def _plain(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def snapshot(obj: Any, fields: list[str] | None = None) -> dict:
    if obj is None:
        return {}
    cols = [c.key for c in inspect(obj).mapper.column_attrs]
    keys = fields or cols
    return {k: _plain(getattr(obj, k)) for k in keys if k in cols and k not in _SECRET_FIELDS}


def diff(before: dict, after: dict) -> tuple[dict, dict]:
    changed = {k for k in after if before.get(k) != after.get(k)}
    return {k: before.get(k) for k in changed}, {k: after[k] for k in changed}


async def write_audit(
    db: AsyncSession,
    *,
    actor_id: int | None,
    action: str,
    entity: str,
    entity_id: int | None = None,
    before: dict | None = None,
    after: dict | None = None,
    branch_id: int | None = None,
    ip: str | None = None,
    note: str | None = None,
) -> None:
    db.add(
        AuditLog(
            actor_id=actor_id,
            action=action,
            entity=entity,
            entity_id=entity_id,
            before=before or {},
            after=after or {},
            branch_id=branch_id,
            ip=ip,
            note=note,
        )
    )
