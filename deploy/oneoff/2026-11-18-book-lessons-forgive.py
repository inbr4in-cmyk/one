import asyncio
import sys

from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import BalanceEntry, Payment, Student
from app.services import balance as bal
from app.services import bookpay

IDS = [1237, 2505, 2506, 2500]
COMMIT = len(sys.argv) > 1 and sys.argv[1] == "commit"


async def main():
    async with SessionLocal() as db:
        fixed = set(await db.scalars(select(BalanceEntry.ref_id).where(BalanceEntry.ref_type == "book_fix")))
        for e in await db.scalars(select(BalanceEntry).where(
                BalanceEntry.kind == "book", BalanceEntry.lessons_delta < 0, BalanceEntry.ref_type == "payment",
                BalanceEntry.student_id.in_(IDS)).order_by(BalanceEntry.id)):
            if e.id in fixed:
                continue
            s = await db.get(Student, e.student_id, with_for_update=True)
            book = await db.get(Payment, e.ref_id)
            lessons = -e.lessons_delta
            print(s.id, s.full_name, "lessons", s.lessons_left, "->", s.lessons_left + lessons, "money stays", s.money_balance)
            if not COMMIT:
                continue
            price, _ = bookpay.cheaper(s.lessons_left + lessons, s.balance_lesson_price or e.lesson_price, book.amount)
            await bal.apply(db, s, "book", lessons=lessons, money=0, price=price, ref=("book_fix", e.id),
                            note=f"Исправление: книга из оплаты больше не уменьшает уроки (+{lessons} ур.), сдача не взыскивается")
            s.balance_lesson_price = price
            src_id = (book.note or "").rpartition("(из оплаты №")[2].rstrip(")")
            src = await db.get(Payment, int(src_id)) if src_id.isdigit() else None
            if src and src.student_id == s.id:
                src.lessons += lessons
                src.lesson_price = src.amount // src.lessons
        if COMMIT:
            await db.commit()
        print("commit" if COMMIT else "preview only")


asyncio.run(main())
