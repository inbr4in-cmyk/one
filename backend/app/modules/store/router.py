"""Books warehouse and sales (ТЗ 12), coins and the coin shop (ТЗ 14)."""

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.core.audit import write_audit
from app.core.deps import DB, Actor, CurrentActor, require
from app.core.errors import bad_request, conflict, forbidden, not_found
from app.core.schemas import ORM
from app.models import (
    Book, BookMovement, BookStock, Branch, CoinEntry, Expense, ExpenseCategory, GroupMember, Payment, Role, ShopItem,
    ShopOrder, Student, User, UserRole,
)
from app.models.finance import PaymentMethod
from app.modules.finance.router import month_bounds
from app.modules.portal.access import my_students, portal_student
from app.modules.students.scope import get_student_scoped
from app.services import coins as coin_svc
from app.services.clock import now, period_of, today
from app.services.messaging import notify_guardians, notify_user
from app.modules.crm.service import crm_people

router = APIRouter(tags=["store"])


async def _expense(db: DB, code: str, branch_id: int, amount: int, ref: str, note: str, actor_id: int) -> None:
    cat = await db.scalar(select(ExpenseCategory.id).where(ExpenseCategory.code == code))
    db.add(Expense(branch_id=branch_id, category_id=cat, amount=amount, spent_on=today(), note=note, source_ref=ref,
                   created_by=actor_id))


async def _stock(db: DB, branch_id: int, book_id: int) -> BookStock:
    st = await db.scalar(select(BookStock).where(BookStock.branch_id == branch_id, BookStock.book_id == book_id).with_for_update())
    if st is None:
        st = BookStock(branch_id=branch_id, book_id=book_id, qty=0)
        db.add(st)
        await db.flush()
    return st


async def _low_stock_alert(db: DB, st: BookStock, book: Book) -> None:
    if st.qty <= st.min_qty:
        for uid in await crm_people(db, st.branch_id, "books", "stock"):
            await notify_user(db, uid, "books", f"Заканчивается книга «{book.title}»", body=f"Осталось {st.qty} шт.",
                              link="/books")


# ---------- catalog ----------
class BookIn(BaseModel):
    title: str = Field(min_length=2, max_length=255)
    level_id: int | None = None
    sale_price: int = Field(ge=0)
    purchase_price: int = Field(ge=0)
    photo_url: str | None = Field(default=None, max_length=255)


class BookOut(ORM):
    id: int
    title: str
    level_id: int | None
    sale_price: int
    purchase_price: int
    photo_url: str | None


@router.get("/books")
async def books(db: DB, actor: Actor = require("books", "view"), branch_id: int | None = None) -> list[dict]:
    branches = actor.branches_for("books", "view")
    if branch_id is not None:
        actor.ensure_branch("books", "view", branch_id)
        branches = {branch_id}
    rows = list(await db.scalars(select(Book).where(Book.archived_at.is_(None)).order_by(Book.title)))
    sq = select(BookStock)
    if branches is not None:
        sq = sq.where(BookStock.branch_id.in_(branches))
    stock: dict[int, dict[int, dict]] = {}
    for s in await db.scalars(sq):
        stock.setdefault(s.book_id, {})[s.branch_id] = {"qty": s.qty, "min_qty": s.min_qty, "low": s.qty <= s.min_qty}
    show_cost = actor.can("books", "stock")
    out = []
    for b in rows:
        d = BookOut.model_validate(b).model_dump()
        if not show_cost:
            d.pop("purchase_price")
        d["stock"] = stock.get(b.id, {})
        out.append(d)
    return out


@router.post("/books", response_model=BookOut, status_code=201)
async def create_book(body: BookIn, db: DB, actor: Actor = require("books", "edit")):
    b = Book(**body.model_dump())
    db.add(b)
    await db.flush()
    await write_audit(db, actor_id=actor.id, action="book.create", entity="book", entity_id=b.id, ip=actor.ip,
                      after=body.model_dump())
    await db.commit()
    return b


@router.patch("/books/{book_id}", response_model=BookOut)
async def update_book(book_id: int, body: BookIn, db: DB, actor: Actor = require("books", "edit")):
    b = await db.get(Book, book_id)
    if b is None or b.archived_at:
        raise not_found("Книга")
    before = BookOut.model_validate(b).model_dump()
    for k, v in body.model_dump().items():
        setattr(b, k, v)
    await write_audit(db, actor_id=actor.id, action="book.update", entity="book", entity_id=b.id, ip=actor.ip,
                      before=before, after=body.model_dump())
    await db.commit()
    return b


# ---------- movements ----------
class StockIn(BaseModel):
    branch_id: int
    book_id: int
    qty: int = Field(gt=0, le=10000)
    unit_price: int = Field(ge=0)
    supplier: str | None = Field(default=None, max_length=255)


@router.post("/books/receive", status_code=201)
async def receive(body: StockIn, db: DB, actor: Actor = require("books", "stock")) -> dict:
    """Purchase: stock goes up and the cost lands in expenses («Закупка книг»)."""
    actor.ensure_branch("books", "stock", body.branch_id)
    book = await db.get(Book, body.book_id)
    if book is None:
        raise not_found("Книга")
    st = await _stock(db, body.branch_id, book.id)
    st.qty += body.qty
    m = BookMovement(at=now(), kind="in", branch_id=body.branch_id, book_id=book.id, qty=body.qty, unit_price=body.unit_price,
                     supplier=body.supplier, actor_id=actor.id)
    db.add(m)
    await db.flush()
    if body.unit_price:
        await _expense(db, "books", body.branch_id, body.qty * body.unit_price, f"book_in:{m.id}",
                       f"«{book.title}» × {body.qty}", actor.id)
    await write_audit(db, actor_id=actor.id, action="book.receive", entity="book_movement", entity_id=m.id,
                      branch_id=body.branch_id, ip=actor.ip, after=body.model_dump())
    await db.commit()
    return {"id": m.id, "qty": st.qty}


class TransferIn(BaseModel):
    from_branch_id: int
    to_branch_id: int
    book_id: int
    qty: int = Field(gt=0, le=10000)


@router.post("/books/transfer", status_code=201)
async def transfer(body: TransferIn, db: DB, actor: Actor = require("books", "stock")) -> dict:
    """Leaves the sender at once; arrives at the receiver only after they confirm."""
    actor.ensure_branch("books", "stock", body.from_branch_id)
    if body.from_branch_id == body.to_branch_id or not await db.get(Branch, body.to_branch_id):
        raise bad_request("Выберите другой филиал")
    st = await _stock(db, body.from_branch_id, body.book_id)
    if st.qty < body.qty:
        raise conflict(f"На складе только {st.qty} шт.")
    st.qty -= body.qty
    m = BookMovement(at=now(), kind="transfer_out", branch_id=body.from_branch_id, to_branch_id=body.to_branch_id,
                     book_id=body.book_id, qty=body.qty, actor_id=actor.id)
    db.add(m)
    await db.flush()
    book = await db.get(Book, body.book_id)
    for uid in await crm_people(db, body.to_branch_id, "books", "stock"):
        await notify_user(db, uid, "books", f"Едут книги: «{book.title}» × {body.qty}", body="Подтвердите получение",
                          link="/books/transfers")
    await write_audit(db, actor_id=actor.id, action="book.transfer", entity="book_movement", entity_id=m.id,
                      branch_id=body.from_branch_id, ip=actor.ip, after=body.model_dump())
    await db.commit()
    return {"id": m.id}


@router.get("/books/transfers")
async def pending_transfers(db: DB, actor: Actor = require("books", "stock")) -> list[dict]:
    q = select(BookMovement).where(BookMovement.kind == "transfer_out", BookMovement.confirmed_at.is_(None))
    allowed = actor.branches_for("books", "stock")
    if allowed is not None:
        q = q.where(BookMovement.to_branch_id.in_(allowed) | BookMovement.branch_id.in_(allowed))
    return [{"id": m.id, "at": m.at, "from_branch_id": m.branch_id, "to_branch_id": m.to_branch_id, "book_id": m.book_id,
             "qty": m.qty} for m in await db.scalars(q.order_by(BookMovement.id))]


@router.post("/books/transfers/{movement_id}/confirm")
async def confirm_transfer(movement_id: int, db: DB, actor: Actor = require("books", "stock")) -> dict:
    m = await db.get(BookMovement, movement_id, with_for_update=True)
    if m is None or m.kind != "transfer_out":
        raise not_found("Перемещение")
    actor.ensure_branch("books", "stock", m.to_branch_id)
    if m.confirmed_at:
        raise conflict("Уже получено")
    m.confirmed_at, m.confirmed_by = now(), actor.id
    st = await _stock(db, m.to_branch_id, m.book_id)
    st.qty += m.qty
    db.add(BookMovement(at=now(), kind="transfer_in", branch_id=m.to_branch_id, book_id=m.book_id, qty=m.qty,
                        reason=f"из перемещения #{m.id}", actor_id=actor.id))
    await write_audit(db, actor_id=actor.id, action="book.transfer_confirm", entity="book_movement", entity_id=m.id,
                      branch_id=m.to_branch_id, ip=actor.ip)
    await db.commit()
    return {"qty": st.qty}


class WriteoffIn(BaseModel):
    branch_id: int
    book_id: int
    qty: int = Field(gt=0, le=10000)
    reason: str = Field(min_length=3, max_length=255)


@router.post("/books/writeoff", status_code=201)
async def writeoff(body: WriteoffIn, db: DB, actor: Actor = require("books", "stock")) -> dict:
    actor.ensure_branch("books", "stock", body.branch_id)
    st = await _stock(db, body.branch_id, body.book_id)
    if st.qty < body.qty:
        raise conflict(f"На складе только {st.qty} шт.")
    st.qty -= body.qty
    m = BookMovement(at=now(), kind="writeoff", branch_id=body.branch_id, book_id=body.book_id, qty=body.qty,
                     reason=body.reason, actor_id=actor.id)
    db.add(m)
    await db.flush()
    await write_audit(db, actor_id=actor.id, action="book.writeoff", entity="book_movement", entity_id=m.id,
                      branch_id=body.branch_id, ip=actor.ip, after=body.model_dump())
    await _low_stock_alert(db, st, await db.get(Book, body.book_id))
    await db.commit()
    return {"qty": st.qty}


class SaleIn(BaseModel):
    student_id: int
    book_id: int
    method: str
    qty: int = Field(default=1, ge=1, le=20)


@router.post("/books/sell", status_code=201)
async def sell(body: SaleIn, db: DB, actor: Actor = require("books", "sell")) -> dict:
    """Only to the school's students: the sale is a separate payment (category «Книги») on the student card."""
    if body.method not in PaymentMethod.ALL:
        raise bad_request("Способ оплаты")
    s = await get_student_scoped(db, actor, body.student_id, "books", "sell", lock=True)
    actor.ensure_branch("books", "sell", s.branch_id)
    book = await db.get(Book, body.book_id)
    if book is None or book.archived_at:
        raise not_found("Книга")
    st = await _stock(db, s.branch_id, book.id)
    if st.qty < body.qty:
        raise conflict(f"В филиале нет этой книги (остаток {st.qty})")
    st.qty -= body.qty
    amount = book.sale_price * body.qty
    p = Payment(student_id=s.id, branch_id=s.branch_id, level_id=book.level_id, category="book", amount=amount,
                method=body.method, received_by=actor.id, paid_at=now(), note=f"Книга «{book.title}» × {body.qty}")
    db.add(p)
    await db.flush()
    m = BookMovement(at=now(), kind="sale", branch_id=s.branch_id, book_id=book.id, qty=body.qty, unit_price=book.sale_price,
                     student_id=s.id, payment_id=p.id, actor_id=actor.id)
    db.add(m)
    await db.flush()
    await notify_guardians(db, s, "book_sale", {"book": book.title, "amount": f"{amount:,}".replace(",", " ")}, ref=("book_sale", m.id))
    await write_audit(db, actor_id=actor.id, action="book.sell", entity="book_movement", entity_id=m.id, branch_id=s.branch_id,
                      ip=actor.ip, after={"student_id": s.id, "book_id": book.id, "qty": body.qty, "amount": amount})
    await _low_stock_alert(db, st, book)
    await db.commit()
    return {"payment_id": p.id, "amount": amount, "left_in_stock": st.qty}


@router.get("/students/{student_id}/books")
async def student_books(student_id: int, db: DB, actor: Actor = require("students", "view")) -> dict:
    """Books the student got, and the one they still need for their current level."""
    s = await get_student_scoped(db, actor, student_id, "students", "view")
    rows = (await db.execute(select(BookMovement, Book.title).join(Book, Book.id == BookMovement.book_id)
                             .where(BookMovement.student_id == s.id, BookMovement.kind == "sale").order_by(BookMovement.at))).all()
    owned = {m.book_id for m, _ in rows}
    needed = [{"id": b.id, "title": b.title, "price": b.sale_price} for b in await db.scalars(
        select(Book).where(Book.level_id == s.level_id, Book.archived_at.is_(None))) if b.id not in owned] if s.level_id else []
    return {"items": [{"at": m.at, "book_id": m.book_id, "title": t, "qty": m.qty, "price": m.unit_price} for m, t in rows],
            "needed": needed}


@router.get("/books/report")
async def books_report(db: DB, actor: Actor = require("books", "stock"), period: str | None = None,
                       branch_id: int | None = None) -> dict:
    period = period or period_of(today())
    _, _, a, b = month_bounds(period)
    branches = actor.branches_for("books", "stock")
    if branch_id is not None:
        actor.ensure_branch("books", "stock", branch_id)
        branches = {branch_id}
    q = (select(BookMovement.kind, BookMovement.book_id, func.sum(BookMovement.qty), func.sum(BookMovement.qty * BookMovement.unit_price))
         .where(BookMovement.at >= a, BookMovement.at < b).group_by(BookMovement.kind, BookMovement.book_id))
    if branches is not None:
        q = q.where(BookMovement.branch_id.in_(branches))
    books = {x.id: x for x in await db.scalars(select(Book))}
    per: dict[int, dict] = {}
    for kind, bid, qty, value in (await db.execute(q)).all():
        r = per.setdefault(bid, {"book_id": bid, "title": books[bid].title})
        r[kind] = int(qty)
        if kind == "sale":
            r["revenue"] = int(value or 0)
            r["profit"] = int(value or 0) - int(qty) * books[bid].purchase_price
    # Students in groups whose level has a book they never bought
    sq = (select(Student.id, Student.full_name, Book.title).join(GroupMember, GroupMember.student_id == Student.id)
          .join(Book, Book.level_id == Student.level_id)
          .where(GroupMember.left_on.is_(None), Student.archived_at.is_(None), Book.archived_at.is_(None),
                 ~select(BookMovement.id).where(BookMovement.student_id == Student.id, BookMovement.book_id == Book.id,
                                               BookMovement.kind == "sale").exists()))
    if branches is not None:
        sq = sq.where(Student.branch_id.in_(branches))
    without = [{"student_id": i, "full_name": n, "book": t} for i, n, t in (await db.execute(sq.limit(500))).all()]
    return {"period": period, "books": list(per.values()), "students_without_book": without,
            "totals": {"revenue": sum(r.get("revenue", 0) for r in per.values()),
                       "profit": sum(r.get("profit", 0) for r in per.values())}}


# ---------- coins ----------
async def _coin_limit(db: DB, actor: Actor) -> int:
    return int(await db.scalar(select(func.coalesce(func.max(Role.coin_limit), 0)).join(UserRole, UserRole.role_id == Role.id)
                               .where(UserRole.user_id == actor.id)))


class AwardIn(BaseModel):
    student_id: int
    amount: int = Field(gt=0, le=10000)
    reason: str = Field(min_length=3, max_length=255)


@router.post("/coins/award", status_code=201)
async def award(body: AwardIn, db: DB, actor: Actor = require("coins", "award")) -> dict:
    """Manual award within the monthly limit of the role, always with a comment (ТЗ 14.1)."""
    s = await get_student_scoped(db, actor, body.student_id, "coins", "award", lock=True)
    await db.get(User, actor.id, with_for_update=True)  # the monthly limit is per giver: serialize their awards
    limit = await _coin_limit(db, actor)
    _, _, a, b = month_bounds(period_of(today()))
    used = int(await db.scalar(select(func.coalesce(func.sum(CoinEntry.delta), 0)).where(
        CoinEntry.actor_id == actor.id, CoinEntry.kind == "manual", CoinEntry.at >= a, CoinEntry.at < b)))
    if used + body.amount > limit:
        raise conflict(f"Месячный лимит {limit} коинов: осталось {max(limit - used, 0)}")
    e = CoinEntry(student_id=s.id, at=now(), kind="manual", delta=body.amount, reason=body.reason, actor_id=actor.id)
    db.add(e)
    await db.flush()
    await write_audit(db, actor_id=actor.id, action="coins.award", entity="student", entity_id=s.id, branch_id=s.branch_id,
                      ip=actor.ip, after={"amount": body.amount, "reason": body.reason})
    if s.user_id:
        await notify_user(db, s.user_id, "coins", f"+{body.amount} коинов", body=body.reason, link="/portal/coins")
    await db.commit()
    return {"balance": await coin_svc.balance(db, s.id), "limit_left": limit - used - body.amount}


@router.post("/coins/writeoff", status_code=201)
async def coin_writeoff(body: AwardIn, db: DB, actor: Actor = require("coins", "writeoff")) -> dict:
    s = await get_student_scoped(db, actor, body.student_id, "coins", "writeoff", lock=True)
    bal = await coin_svc.balance(db, s.id)
    if body.amount > bal:
        raise conflict(f"У ученика только {bal} коинов")
    db.add(CoinEntry(student_id=s.id, at=now(), kind="writeoff", delta=-body.amount, reason=body.reason, actor_id=actor.id))
    await write_audit(db, actor_id=actor.id, action="coins.writeoff", entity="student", entity_id=s.id, branch_id=s.branch_id,
                      ip=actor.ip, after={"amount": body.amount, "reason": body.reason})
    await db.commit()
    return {"balance": bal - body.amount}


@router.get("/students/{student_id}/coins")
async def student_coins(student_id: int, db: DB, actor: Actor = require("coins", "view")) -> dict:
    s = await get_student_scoped(db, actor, student_id, "coins", "view")
    rows = await db.scalars(select(CoinEntry).where(CoinEntry.student_id == s.id).order_by(CoinEntry.id.desc()).limit(200))
    return {"balance": await coin_svc.balance(db, s.id),
            "items": [{"at": e.at, "kind": e.kind, "delta": e.delta, "reason": e.reason} for e in rows]}


@router.get("/coins/top")
async def coins_top(db: DB, actor: CurrentActor, group_id: int | None = None, branch_id: int | None = None,
                    limit: int = 20) -> list[dict]:
    """Leaderboard (ТЗ 14.3). Staff see their scope; students and parents see their group or branch, first names only."""
    if actor.is_staff:
        allowed = actor.branches_for("coins", "view")
        if branch_id is not None:
            actor.ensure_branch("coins", "view", branch_id)
        branches = {branch_id} if branch_id is not None else allowed
    else:
        kids = await my_students(db, actor)
        if not kids:
            return []
        branches = {k.branch_id for k in kids}
        if branch_id is not None and branch_id not in branches:
            raise forbidden()
        if branch_id is not None:
            branches = {branch_id}
        if group_id is not None and not await db.scalar(select(GroupMember.id).where(
                GroupMember.group_id == group_id, GroupMember.student_id.in_([k.id for k in kids]), GroupMember.left_on.is_(None))):
            raise forbidden()
    total = func.sum(CoinEntry.delta).label("total")
    q = (select(Student.id, Student.full_name, Student.branch_id, total).join(CoinEntry, CoinEntry.student_id == Student.id)
         .where(Student.archived_at.is_(None), CoinEntry.kind.not_in(("order_hold", "order_release", "order_spend")))
         .group_by(Student.id).order_by(total.desc()).limit(min(limit, 100)))
    if group_id:
        q = q.where(Student.id.in_(select(GroupMember.student_id).where(GroupMember.group_id == group_id,
                                                                         GroupMember.left_on.is_(None))))
    if branches is not None:
        q = q.where(Student.branch_id.in_(branches))
    staff = actor.is_staff
    return [{"student_id": i if staff else None, "name": n if staff else n.split(" ")[0], "branch_id": b, "coins": int(t)}
            for i, n, b, t in (await db.execute(q)).all()]


# ---------- shop ----------
class ItemIn(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    photo_url: str | None = Field(default=None, max_length=255)
    icon: str | None = Field(default=None, max_length=32)
    price_coins: int = Field(gt=0, le=1_000_000)
    stock: int = Field(ge=0, le=100000)
    cost: int = Field(default=0, ge=0)
    branch_id: int | None = None


@router.get("/shop/items")
async def shop_items(db: DB, actor: CurrentActor, branch_id: int | None = None) -> list[dict]:
    q = select(ShopItem).where(ShopItem.archived_at.is_(None))
    if branch_id:
        q = q.where((ShopItem.branch_id == branch_id) | ShopItem.branch_id.is_(None))
    show_cost = actor.can("shop", "edit")
    return [{"id": i.id, "name": i.name, "photo_url": i.photo_url, "icon": i.icon, "price_coins": i.price_coins,
             "stock": i.stock, "branch_id": i.branch_id, **({"cost": i.cost} if show_cost else {})}
            for i in await db.scalars(q.order_by(ShopItem.price_coins))]


@router.post("/shop/items", status_code=201)
async def create_item(body: ItemIn, db: DB, actor: Actor = require("shop", "edit")) -> dict:
    if body.branch_id is not None:
        actor.ensure_branch("shop", "edit", body.branch_id)
    i = ShopItem(**body.model_dump())
    db.add(i)
    await db.flush()
    await write_audit(db, actor_id=actor.id, action="shop.item_create", entity="shop_item", entity_id=i.id, ip=actor.ip,
                      after=body.model_dump())
    await db.commit()
    return {"id": i.id}


@router.patch("/shop/items/{item_id}")
async def update_item(item_id: int, body: ItemIn, db: DB, actor: Actor = require("shop", "edit")) -> dict:
    i = await db.get(ShopItem, item_id)
    if i is None or i.archived_at:
        raise not_found("Товар")
    for b in {i.branch_id, body.branch_id}:
        if b is None and actor.branches_for("shop", "edit") is not None:
            raise forbidden("Общие товары сети меняет владелец")
        if b is not None:
            actor.ensure_branch("shop", "edit", b)
    for k, v in body.model_dump().items():
        setattr(i, k, v)
    await write_audit(db, actor_id=actor.id, action="shop.item_update", entity="shop_item", entity_id=i.id, ip=actor.ip,
                      after=body.model_dump())
    await db.commit()
    return {"id": i.id}


async def _my_student(db: DB, actor: Actor, student_id: int) -> Student:
    """A student orders for themselves, a parent for their child; staff can't spend a child's coins."""
    return await portal_student(db, actor, student_id, allow_blocked=True)


class OrderIn(BaseModel):
    student_id: int
    item_id: int


@router.post("/shop/orders", status_code=201)
async def place_order(body: OrderIn, db: DB, actor: CurrentActor) -> dict:
    s = await _my_student(db, actor, body.student_id)
    if s.access_blocked_at:
        raise forbidden("Доступ приостановлен до оплаты")
    item = await db.get(ShopItem, body.item_id, with_for_update=True)
    if item is None or item.archived_at:
        raise not_found("Товар")
    if item.stock <= 0:
        raise conflict("Товар закончился")
    # Serialize per student so two taps can't spend the same coins twice.
    await db.get(Student, s.id, with_for_update=True)
    bal = await coin_svc.balance(db, s.id)
    if bal < item.price_coins:
        raise conflict(f"Не хватает {item.price_coins - bal} коинов")
    item.stock -= 1
    o = ShopOrder(student_id=s.id, item_id=item.id, branch_id=item.branch_id or s.branch_id, coins=item.price_coins, status="placed")
    db.add(o)
    await db.flush()
    db.add(CoinEntry(student_id=s.id, at=now(), kind="order_hold", delta=-item.price_coins, reason=item.name,
                     ref_type="order", ref_id=o.id, actor_id=actor.id))
    for uid in await crm_people(db, o.branch_id, "shop", "issue"):
        await notify_user(db, uid, "shop", f"Заказ: {item.name}", body=s.full_name, link="/shop/orders")
    await write_audit(db, actor_id=actor.id, action="shop.order", entity="shop_order", entity_id=o.id, branch_id=o.branch_id,
                      ip=actor.ip, after={"student_id": s.id, "item_id": item.id, "coins": item.price_coins})
    await db.commit()
    return {"id": o.id, "status": o.status, "balance": bal - item.price_coins}


@router.get("/shop/orders")
async def orders(db: DB, actor: CurrentActor, status: str | None = None, student_id: int | None = None) -> list[dict]:
    q = select(ShopOrder, ShopItem.name, Student.full_name).join(ShopItem, ShopItem.id == ShopOrder.item_id) \
        .join(Student, Student.id == ShopOrder.student_id)
    if actor.is_staff:
        allowed = actor.branches_for("shop", "view")
        if allowed is not None:
            q = q.where(ShopOrder.branch_id.in_(allowed))
        if student_id:
            q = q.where(ShopOrder.student_id == student_id)
    else:
        if not student_id:
            raise bad_request("Укажите ученика")
        s = await _my_student(db, actor, student_id)
        q = q.where(ShopOrder.student_id == s.id)
    if status:
        q = q.where(ShopOrder.status == status)
    return [{"id": o.id, "student_id": o.student_id, "student": n, "item": i, "coins": o.coins, "status": o.status,
             "branch_id": o.branch_id, "created_at": o.created_at, "issued_at": o.issued_at}
            for o, i, n in (await db.execute(q.order_by(ShopOrder.id.desc()).limit(300))).all()]


class OrderStatusIn(BaseModel):
    status: str = Field(pattern="^(ready|issued|cancelled)$")


@router.post("/shop/orders/{order_id}/status")
async def order_status(order_id: int, body: OrderStatusIn, db: DB, actor: CurrentActor) -> dict:
    o = await db.get(ShopOrder, order_id, with_for_update=True)
    if o is None:
        raise not_found("Заказ")
    staff = actor.is_staff and actor.can("shop", "issue")
    if staff:
        actor.ensure_branch("shop", "issue", o.branch_id)
    else:
        await _my_student(db, actor, o.student_id)
        if body.status != "cancelled" or o.status != "placed":
            raise forbidden("Отменить можно только новый заказ")
    allowed = {"placed": {"ready", "issued", "cancelled"}, "ready": {"issued", "cancelled"}}
    if body.status not in allowed.get(o.status, set()):
        raise conflict("Заказ уже закрыт")
    item = await db.get(ShopItem, o.item_id)
    if body.status == "cancelled":
        db.add(CoinEntry(student_id=o.student_id, at=now(), kind="order_release", delta=o.coins, reason="Заказ отменён",
                         ref_type="order", ref_id=o.id, actor_id=actor.id))
        item.stock += 1
    elif body.status == "issued":
        o.issued_by, o.issued_at = actor.id, now()
        if item.cost:
            await _expense(db, "shop", o.branch_id, item.cost, f"shop_order:{o.id}", f"Магазин коинов: {item.name}", actor.id)
    o.status = body.status
    s = await db.get(Student, o.student_id)
    if s.user_id and body.status == "ready":
        await notify_user(db, s.user_id, "shop", f"Заказ готов: {item.name}", body="Заберите на ресепшене", link="/portal/shop")
    await write_audit(db, actor_id=actor.id, action=f"shop.order_{body.status}", entity="shop_order", entity_id=o.id,
                      branch_id=o.branch_id, ip=actor.ip)
    await db.commit()
    return {"id": o.id, "status": o.status}

