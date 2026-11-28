"""Lesson plan of a level: its items, what a group's coming lessons will be, the fill from the school's file."""
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Lesson, Level, PlanItem
from app.models.learning import LessonStatus

TESTS = ("progress_test", "final_test")


def kind_of(title: str) -> str:
    t = title.lower()
    return "final_test" if "final test" in t else "progress_test" if "progress test" in t else "lesson"


async def items(db: AsyncSession, level_id: int | None) -> list[PlanItem]:
    if not level_id:
        return []
    return list(await db.scalars(select(PlanItem).where(PlanItem.level_id == level_id, PlanItem.archived_at.is_(None))
                                 .order_by(PlanItem.position, PlanItem.id)))


def numbered(rows: list[PlanItem]) -> list[dict]:
    """Plan rows with the number through the level and the number inside the month («Месяц 2 · Урок 5»)."""
    out, in_month = [], {}
    for i, x in enumerate(rows, 1):
        in_month[x.month] = in_month.get(x.month, 0) + 1
        out.append({"id": x.id, "no": i, "month": x.month, "num": in_month[x.month], "title": x.title, "kind": x.kind})
    return out


def plannable(x: Lesson) -> bool:
    return bool(x.level_id) and not x.is_support and not x.is_trial


async def forecast(db: AsyncSession, lessons: list[Lesson]) -> dict[int, tuple[dict, bool]]:
    """lesson id → (plan row, is a guess). A held lesson shows what the teacher picked. A coming lesson of a group
    shows the next rows after the group's last picked one; a group that has not held a lesson yet starts from the
    first row. Groups already studying get no guess until a teacher picks a row once."""
    cand = [x for x in lessons if plannable(x) and x.status != LessonStatus.CANCELLED]
    if not cand:
        return {}
    plans = {lid: numbered(await items(db, lid)) for lid in {x.level_id for x in cand}}
    by_id = {r["id"]: r for rows in plans.values() for r in rows}
    out: dict[int, tuple[dict, bool]] = {}
    picked_ids = {x.plan_item_id for x in cand if x.plan_item_id} - set(by_id)
    if picked_ids:  # an item removed from the plan later: still shown on the lesson it was taught at
        for it in await db.scalars(select(PlanItem).where(PlanItem.id.in_(picked_ids))):
            by_id[it.id] = {"id": it.id, "no": 0, "month": it.month, "num": 0, "title": it.title, "kind": it.kind}
    for x in cand:
        if x.plan_item_id and x.plan_item_id in by_id:
            out[x.id] = (by_id[x.plan_item_id], False)
    gids = {x.group_id for x in cand if x.group_id and x.id not in out and x.attendance_marked_at is None and plans.get(x.level_id)}
    if not gids:
        return out
    last: dict[int, tuple[datetime, int]] = {}
    for gid, at, pid in (await db.execute(select(Lesson.group_id, Lesson.starts_at, Lesson.plan_item_id).where(
            Lesson.group_id.in_(gids), Lesson.plan_item_id.is_not(None), Lesson.status != LessonStatus.CANCELLED)
            .order_by(Lesson.starts_at))).all():
        last[gid] = (at, pid)
    held = set((await db.scalars(select(Lesson.group_id).where(
        Lesson.group_id.in_(gids), Lesson.attendance_marked_at.is_not(None), Lesson.is_support.is_(False),
        Lesson.is_trial.is_(False)).distinct())).all())
    coming: dict[int, list[tuple[datetime, int, int | None]]] = {}
    for gid, at, lid, lvl in (await db.execute(select(Lesson.group_id, Lesson.starts_at, Lesson.id, Lesson.level_id).where(
            Lesson.group_id.in_(gids), Lesson.attendance_marked_at.is_(None), Lesson.status != LessonStatus.CANCELLED,
            Lesson.is_support.is_(False), Lesson.is_trial.is_(False)).order_by(Lesson.starts_at))).all():
        coming.setdefault(gid, []).append((at, lid, lvl))
    for gid in gids:
        if gid in last:
            since, pid = last[gid]
            row = by_id.get(pid)
            idx = row["no"] if row and row["no"] else None  # 1-based number of the last taught row = index of the next
        elif gid in held:
            continue
        else:
            since, idx = None, 0
        if idx is None:
            continue
        for at, lid, lvl in coming.get(gid, []):
            if since is not None and at <= since:
                continue
            rows = plans.get(lvl) or []
            if idx >= len(rows):
                break
            out.setdefault(lid, (rows[idx], True))
            idx += 1
    return out


async def next_row(db: AsyncSession, item: PlanItem) -> PlanItem | None:
    return await db.scalar(select(PlanItem).where(PlanItem.level_id == item.level_id, PlanItem.archived_at.is_(None),
                                                  PlanItem.position > item.position).order_by(PlanItem.position, PlanItem.id).limit(1))


async def replace(db: AsyncSession, level_id: int, rows: list[dict]) -> None:
    """Save the plan as edited: rows with an id are kept (and may move), new ones are added, missing ones archived."""
    from app.services.clock import now

    have = {x.id: x for x in await items(db, level_id)}
    seen = set()
    for pos, r in enumerate(rows, 1):
        it = have.get(r.get("id") or 0)
        if it is None:
            it = PlanItem(level_id=level_id, position=pos, month=r["month"], title=r["title"], kind=r["kind"])
            db.add(it)
        else:
            it.position, it.month, it.title, it.kind = pos, r["month"], r["title"], r["kind"]
            seen.add(it.id)
    for i, it in have.items():
        if i not in seen:
            it.archived_at = now()
    await db.flush()


async def seed(db: AsyncSession) -> str:
    """Fill the plans of Beginner and Elementary from the school's file where a level has no plan yet."""
    from app.services.plan_data import PLANS

    lines = []
    for lv in await db.scalars(select(Level).where(Level.archived_at.is_(None)).order_by(Level.order)):
        key = next((k for k in PLANS if lv.name.strip().lower().startswith(k) or lv.code.strip().lower() == k[:3]), None)
        n = await db.scalar(select(func.count()).select_from(PlanItem).where(PlanItem.level_id == lv.id, PlanItem.archived_at.is_(None)))
        if key is None:
            lines.append(f"- {lv.id} {lv.code} «{lv.name}»: no file plan, rows now {n}")
        elif n:
            lines.append(f"= {lv.id} {lv.code} «{lv.name}»: already has {n} rows, kept")
        else:
            await replace(db, lv.id, [{"month": m, "title": t, "kind": kind_of(t)} for m, t in PLANS[key]])
            lines.append(f"+ {lv.id} {lv.code} «{lv.name}»: filled {len(PLANS[key])} rows from «{key}»")
    await db.commit()
    return "\n".join(lines)
