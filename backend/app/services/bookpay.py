"""Paying for a book out of a course payment the student already made («из оплаты»)."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BalanceEntry, Payment, Student
from app.services import balance as bal


def lesson_price(s: Student, p: Payment) -> int:
    return s.balance_lesson_price or p.lesson_price or 0


def capacity(s: Student, p: Payment) -> int:
    """How much of payment `p` can still become a book payment: not more than is left of the payment itself and
    not more than is still unspent on the student's balance (money + lessons at their price)."""
    on_balance = max(s.money_balance, 0) + max(s.lessons_left, 0) * lesson_price(s, p)
    return max(0, min(p.amount - p.refunded, on_balance))


async def source(db: AsyncSession, s: Student, amount: int = 1, lock: bool = False) -> Payment | None:
    """The newest course payment entered on the site that still covers `amount`."""
    q = select(Payment).where(Payment.student_id == s.id, Payment.category == "course", Payment.source.is_(None),
                              Payment.amount - Payment.refunded >= amount).order_by(Payment.paid_at.desc(), Payment.id.desc())
    for p in await db.scalars(q.with_for_update() if lock else q):
        if capacity(s, p) >= amount:
            return p
    return None


def cheaper(lessons_left: int, price: int, amount: int) -> tuple[int, int]:
    """The book's `amount` comes out of the value of the lessons still on the balance: their number stays, each one
    costs less. Returns (new lesson price, what the lessons could not cover and has to come from the money balance)."""
    if lessons_left <= 0:
        return price, amount
    covered = min(amount, lessons_left * price)
    return (lessons_left * price - covered) // lessons_left, amount - covered


async def take(db: AsyncSession, s: Student, src: Payment, amount: int, *, ref: tuple[str, int], actor_id: int | None,
               note: str) -> None:
    """Owner's rule (18.11.2026): 33 500 paid for 12 lessons, a 4 000 book out of it → still 12 lessons, the course
    payment becomes 29 500 and the book payment 4 000. Paid lessons are never taken away for a book."""
    price, from_money = cheaper(s.lessons_left, lesson_price(s, src), amount)
    await bal.apply(db, s, "book", lessons=0, money=-from_money, price=price, ref=ref, actor_id=actor_id, note=note)
    if s.lessons_left > 0:
        s.balance_lesson_price = price
    src.amount -= amount
    if src.lessons:
        src.lesson_price = src.amount // src.lessons


async def restore_lessons(db: AsyncSession, commit: bool) -> dict:
    """One-off for books sold «из оплаты» before 18.11.2026, when the book took paid lessons away: the lessons come
    back, the change that went to the money balance is taken back, the lessons just cost less. Safe to repeat: a
    corrected sale is marked in the balance history. A sale is skipped (and listed) when the student has already
    spent that change, so nobody ends up with a debt they do not know about."""
    fixed = set(await db.scalars(select(BalanceEntry.ref_id).where(BalanceEntry.ref_type == "book_fix")))
    rows = list(await db.scalars(select(BalanceEntry).where(
        BalanceEntry.kind == "book", BalanceEntry.lessons_delta < 0, BalanceEntry.ref_type == "payment").order_by(BalanceEntry.id)))
    done, skipped = [], []
    for e in rows:
        if e.id in fixed:
            continue
        s = await db.get(Student, e.student_id, with_for_update=True)
        book = await db.get(Payment, e.ref_id)
        lessons, change = -e.lessons_delta, e.money_delta
        line = {"student_id": s.id, "student": s.full_name, "lessons_back": lessons, "money_back": change,
                "lessons_now": s.lessons_left, "money_now": s.money_balance}
        if book is None or s.money_balance - change < 0:
            skipped.append(line | {"why": "сдача с книги уже потрачена" if book else "оплата за книгу не найдена"})
            continue
        done.append(line)
        if not commit:
            continue
        left = s.lessons_left + lessons
        price, _ = cheaper(left, s.balance_lesson_price or e.lesson_price, book.amount)
        await bal.apply(db, s, "book", lessons=lessons, money=-change, price=price, ref=("book_fix", e.id),
                        note=f"Исправление: книга из оплаты больше не уменьшает уроки (+{lessons} ур.)")
        s.balance_lesson_price = price
        src_id = (book.note or "").rpartition("(из оплаты №")[2].rstrip(")")
        src = await db.get(Payment, int(src_id)) if src_id.isdigit() else None
        if src and src.student_id == s.id:
            src.lessons += lessons
            src.lesson_price = src.amount // src.lessons
    if commit:
        await db.commit()
    return {"commit": commit, "fixed": len(done), "skipped": len(skipped), "rows": done, "need_manual": skipped}
