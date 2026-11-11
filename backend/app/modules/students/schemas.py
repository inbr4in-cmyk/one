from datetime import date, datetime

from pydantic import BaseModel, Field

from app.core.schemas import In, ORM


class GuardianIn(In):
    full_name: str = Field(min_length=2, max_length=255)
    phone: str = Field(max_length=32)
    relation: str | None = Field(default=None, max_length=255)
    whatsapp: str | None = Field(default=None, max_length=32)
    notify: bool = True
    locale: str = Field(default="ru", pattern="^(ru|kk)$")


class StudentIn(In):
    full_name: str = Field(min_length=2, max_length=255)
    birth_date: date | None = None
    phone: str | None = Field(default=None, max_length=32)
    branch_id: int
    level_id: int | None = None
    source: str | None = Field(default=None, max_length=255)
    status: str = "active"
    notes: str | None = Field(default=None, max_length=4000)
    guardians: list[GuardianIn] = []
    create_account: bool = True
    contract_no: str | None = Field(default=None, max_length=64)
    contract_date: date | None = None


class StudentPatch(In):
    full_name: str | None = Field(default=None, max_length=255)
    birth_date: date | None = None
    phone: str | None = Field(default=None, max_length=32)
    level_id: int | None = None
    source: str | None = Field(default=None, max_length=255)
    notes: str | None = Field(default=None, max_length=4000)
    photo_url: str | None = Field(default=None, max_length=255)
    contract_no: str | None = Field(default=None, max_length=64)
    contract_date: date | None = None
    # manual status: studying / finished the course / left (freezes have their own flow)
    status: str | None = Field(default=None, pattern="^(active|finished|left)$")


class GuardianOut(BaseModel):
    id: int
    user_id: int
    full_name: str
    phone: str | None
    relation: str | None
    notify: bool


class StudentListOut(BaseModel):
    id: int
    full_name: str
    phone: str | None
    branch_id: int
    level_id: int | None
    status: str
    group_names: list[str] = []
    lessons_left: int
    money_balance: int
    last_payment_at: datetime | None
    last_visit_at: datetime | None
    age: int | None = None


class BalanceOut(BaseModel):
    lessons_paid: int
    lessons_done: int
    lessons_left: int
    money_balance: int
    lesson_price: int


class StudentOut(StudentListOut):
    birth_date: date | None
    photo_url: str | None
    source: str | None
    notes: str | None
    contract_no: str | None = None
    contract_date: date | None = None
    sales_user_id: int | None
    office_user_id: int | None
    user_id: int | None
    stars: int
    coins: int = 0
    balance: BalanceOut
    guardians: list[GuardianOut] = []
    groups: list[dict] = []
    created_at: datetime
    archived_at: datetime | None
    # Current subscription (абонемент): {name, valid_to} or None
    subscription: dict | None = None


class LedgerOut(ORM):
    id: int
    at: datetime
    kind: str
    lessons_delta: int
    money_delta: int
    lesson_price: int
    lessons_after: int
    money_after: int
    note: str | None


class TransferIn(In):
    to_group_id: int
    reason: str | None = Field(default=None, max_length=255)


class TransferPreview(BaseModel):
    from_group: str | None
    to_group: str
    from_level: str | None
    to_level: str
    same_price: bool
    lessons_before: int
    money_before: int
    old_price: int
    new_price: int
    value: int
    lessons_after: int
    money_after: int
    book_hint: str | None = None


class FreezeIn(In):
    starts_on: date
    ends_on: date
    reason: str | None = Field(default=None, max_length=255)
