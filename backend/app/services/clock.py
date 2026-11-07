from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

SCHOOL_TZ = ZoneInfo("Asia/Almaty")  # Shymkent, UTC+5


def now() -> datetime:
    return datetime.now(UTC)


def local(dt: datetime) -> datetime:
    return dt.astimezone(SCHOOL_TZ)


def today() -> date:
    return now().astimezone(SCHOOL_TZ).date()


def at_local(d: date, t: time) -> datetime:
    return datetime.combine(d, t, tzinfo=SCHOOL_TZ).astimezone(UTC)


def end_of_local_day(dt: datetime) -> datetime:
    d = local(dt).date()
    return datetime.combine(d + timedelta(days=1), time(0), tzinfo=SCHOOL_TZ).astimezone(UTC)


def period_of(dt: datetime | date) -> str:
    d = local(dt).date() if isinstance(dt, datetime) else dt
    return f"{d.year:04d}-{d.month:02d}"


def local_day_start(d: date) -> datetime:
    """00:00 of a school-local calendar day, as a UTC instant."""
    return at_local(d, time(0))


def local_range(date_from: date | None, date_to: date | None) -> tuple[datetime | None, datetime | None]:
    """A [from, to] range of school-local calendar days, both ends inclusive → [start, end) in UTC.
    The one helper for every date filter (schedule, payments, CRM analytics): «today–today» is the whole day."""
    start = local_day_start(date_from) if date_from else None
    end = local_day_start(date_to + timedelta(days=1)) if date_to else None
    return start, end


def parse_day(value: str | date | datetime | None) -> date | None:
    """Query parameter → school-local date. Accepts «2026-11-04» or an ISO datetime (taken in school time)."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return local(value).date() if value.tzinfo else value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(value[:10]) if len(value) <= 10 else parse_day(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError:
        from fastapi import HTTPException

        raise HTTPException(422, "Дата в формате ГГГГ-ММ-ДД") from None
