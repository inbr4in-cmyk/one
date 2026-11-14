from sqlalchemy import Boolean, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, TimestampMixin
from app.models._types import DT, DTN, D, DateN, IntN, StrN, TextN, fk


class Chat(IdMixin, TimestampMixin, Base):
    __tablename__ = "chats"

    kind: Mapped[str] = mapped_column(String(16))  # group | direct
    title: Mapped[StrN]
    group_id: Mapped[int | None] = fk("groups.id", nullable=True)
    branch_id: Mapped[int | None] = fk("branches.id", nullable=True)
    # For direct chats: sorted "a:b" user ids, so a pair has exactly one chat.
    direct_key: Mapped[StrN] = mapped_column(String(64), unique=True, default=None)
    # Optional context: the student a parent ↔ teacher chat is about.
    about_student_id: Mapped[int | None] = fk("students.id", nullable=True)
    last_message_at: Mapped[DTN]


class ChatMember(IdMixin, Base):
    __tablename__ = "chat_members"
    __table_args__ = (UniqueConstraint("chat_id", "user_id"),)

    chat_id: Mapped[int] = fk("chats.id")
    user_id: Mapped[int] = fk("users.id")
    joined_on: Mapped[D]
    left_on: Mapped[DateN]
    last_read_id: Mapped[IntN]
    muted: Mapped[bool] = mapped_column(Boolean, default=False)


class ChatMessage(IdMixin, Base):
    __tablename__ = "chat_messages"

    chat_id: Mapped[int] = fk("chats.id")
    sender_id: Mapped[int] = fk("users.id")
    at: Mapped[DT]
    kind: Mapped[str] = mapped_column(String(16), default="text")  # text | image | file | voice | system
    text: Mapped[TextN]
    file_url: Mapped[StrN]
    file_name: Mapped[StrN]
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    edited_at: Mapped[DTN]
    # Messages are kept for quality control (ТЗ 8); "deleted" only hides them from members.
    hidden_at: Mapped[DTN]
