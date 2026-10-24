"""Books warehouse, coins and the coin shop."""

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import ArchiveMixin, Base, IdMixin, TimestampMixin
from app.models._types import DT, DTN, Int, IntN, Money, StrN, fk


class Book(IdMixin, TimestampMixin, ArchiveMixin, Base):
    __tablename__ = "books"

    title: Mapped[str] = mapped_column(String(255))
    level_id: Mapped[int | None] = fk("levels.id", nullable=True)
    sale_price: Mapped[Money]
    purchase_price: Mapped[Money]
    photo_url: Mapped[StrN]


class BookStock(IdMixin, Base):
    __tablename__ = "book_stock"
    __table_args__ = (UniqueConstraint("branch_id", "book_id"),)

    branch_id: Mapped[int] = fk("branches.id")
    book_id: Mapped[int] = fk("books.id")
    qty: Mapped[Int]
    min_qty: Mapped[int] = mapped_column(default=5)


class BookMovement(IdMixin, Base):
    __tablename__ = "book_movements"

    at: Mapped[DT]
    # in | sale | transfer_out | transfer_in | writeoff
    kind: Mapped[str] = mapped_column(String(16))
    branch_id: Mapped[int] = fk("branches.id")
    book_id: Mapped[int] = fk("books.id")
    qty: Mapped[int]
    unit_price: Mapped[Money]
    student_id: Mapped[int | None] = fk("students.id", nullable=True)
    payment_id: Mapped[int | None] = fk("payments.id", nullable=True)
    supplier: Mapped[StrN]
    reason: Mapped[StrN]
    to_branch_id: Mapped[int | None] = fk("branches.id", nullable=True)
    # transfer: waiting for the receiving branch to confirm
    confirmed_at: Mapped[DTN]
    confirmed_by: Mapped[IntN]
    actor_id: Mapped[int] = fk("users.id")


class CoinEntry(IdMixin, Base):
    __tablename__ = "coin_entries"
    # Automatic awards are idempotent per fact.
    __table_args__ = (UniqueConstraint("student_id", "kind", "ref_type", "ref_id"),)

    student_id: Mapped[int] = fk("students.id")
    at: Mapped[DT]
    # attendance | perfect_month | homework | final_test | birthday | referral | manual | writeoff | order_hold | order_release
    kind: Mapped[str] = mapped_column(String(24))
    delta: Mapped[int]
    reason: Mapped[StrN]
    ref_type: Mapped[StrN]
    ref_id: Mapped[IntN]
    actor_id: Mapped[IntN]


class ShopItem(IdMixin, TimestampMixin, ArchiveMixin, Base):
    __tablename__ = "shop_items"

    name: Mapped[str] = mapped_column(String(255))
    photo_url: Mapped[StrN]
    icon: Mapped[StrN]
    price_coins: Mapped[int]
    stock: Mapped[Int]
    cost: Mapped[Money]  # cost price, goes to expenses
    branch_id: Mapped[int | None] = fk("branches.id", nullable=True)


class ShopOrder(IdMixin, TimestampMixin, Base):
    __tablename__ = "shop_orders"

    student_id: Mapped[int] = fk("students.id")
    item_id: Mapped[int] = fk("shop_items.id")
    branch_id: Mapped[int] = fk("branches.id")
    coins: Mapped[int]
    # placed (coins reserved) | ready | issued (coins spent) | cancelled (coins returned)
    status: Mapped[str] = mapped_column(String(16), default="placed")
    issued_by: Mapped[IntN]
    issued_at: Mapped[DTN]
