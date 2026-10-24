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
