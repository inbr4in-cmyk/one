from datetime import date, datetime, time
from typing import Annotated, Any

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Integer, String, Text, Time
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import mapped_column

# Money is always integer tenge; never floats.
Money = Annotated[int, mapped_column(BigInteger, default=0, nullable=False)]
Str = Annotated[str, mapped_column(String(255))]
StrN = Annotated[str | None, mapped_column(String(255), default=None)]
TextN = Annotated[str | None, mapped_column(Text, default=None)]
Int = Annotated[int, mapped_column(Integer, default=0, nullable=False)]
IntN = Annotated[int | None, mapped_column(Integer, default=None)]
DT = Annotated[datetime, mapped_column(DateTime(timezone=True))]
DTN = Annotated[datetime | None, mapped_column(DateTime(timezone=True), default=None)]
DateN = Annotated[date | None, mapped_column(Date, default=None)]
D = Annotated[date, mapped_column(Date)]
TimeT = Annotated[time, mapped_column(Time)]
Json = Annotated[Any, mapped_column(JSONB, default=dict)]


def fk(target: str, nullable: bool = False, ondelete: str = "RESTRICT", index: bool = True, use_alter: bool = False):
    return mapped_column(
        BigInteger,
        ForeignKey(target, ondelete=ondelete, use_alter=use_alter),
        nullable=nullable,
        index=index,
        default=None,
    )
