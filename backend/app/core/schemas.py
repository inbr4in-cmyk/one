from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, field_validator

T = TypeVar("T")


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


class In(BaseModel):
    """Base for request bodies (QA C-7): every string is capped, and a datetime without a time zone is read as
    school time (Asia/Almaty) instead of failing later on a naive/aware comparison."""

    model_config = ConfigDict(str_max_length=10_000)

    @field_validator("*", mode="after")
    @classmethod
    def _aware(cls, v):
        if isinstance(v, datetime) and v.tzinfo is None:
            from app.services.clock import SCHOOL_TZ

            return v.replace(tzinfo=SCHOOL_TZ)
        return v
