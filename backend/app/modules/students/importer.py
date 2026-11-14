"""Excel import of existing students (moving from spreadsheets). Always preview first, then commit the same file."""

import io
from datetime import date, datetime

from fastapi.concurrency import run_in_threadpool
from fastapi import APIRouter, File, Query, UploadFile
from sqlalchemy import func, select

from app.core.audit import write_audit
from app.core.config import get_settings
from app.core.deps import DB, Actor, require
from app.core.errors import bad_request, forbidden
from app.core.security import normalize_phone
from app.models import Branch, Group, GroupMember, Level, Student
from app.models.identity import UserKind
from app.models.learning import StudentStatus
from app.modules.students.router import add_guardian, upsert_portal_user
from app.modules.students.schemas import GuardianIn
from app.services import balance as bal
from app.services import chats
from app.services.clock import today

router = APIRouter(tags=["import"])

# Header → field. Russian headers as in the school's current spreadsheets; a few aliases accepted.
COLUMNS = {
    "фио": "full_name", "ученик": "full_name", "телефон": "phone", "дата рождения": "birth_date", "филиал": "branch",
    "уровень": "level", "группа": "group", "осталось уроков": "lessons_left", "цена урока": "lesson_price",
    "родитель": "parent_name", "фио родителя": "parent_name", "телефон родителя": "parent_phone", "кем приходится": "relation",
}
MAX_ROWS = 3000


def _cell(v) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _phone(v) -> str | None:
    s = _cell(v)
    if not s:
        return None
    p = normalize_phone(s)
    if len(p) != 12 or not p.startswith("+7"):
        raise ValueError(f"неверный телефон «{s}»")
    return p


def _date(v) -> date | None:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = _cell(v)
    if not s:
        return None
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    raise ValueError("дата в формате ДД.ММ.ГГГГ")


def _read_rows(data: bytes) -> list[tuple]:
    """Parsing XLSX is CPU work: it runs in a worker thread, so the API keeps serving others (QA H-14)."""
    from openpyxl import load_workbook

    try:
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as e:  # noqa: BLE001 — any broken file is the user's error
        raise ValueError("bad file") from e
    try:
        out = []
        for row in wb.worksheets[0].iter_rows(values_only=True):
            out.append(tuple(row[:40]))
            if len(out) > MAX_ROWS + 1:
                break
        return out
    finally:
        wb.close()


async def _parse(db: DB, data: bytes, actor: Actor) -> tuple[list[dict], list[dict]]:
    try:
        all_rows = await run_in_threadpool(_read_rows, data)
    except ValueError as e:
        raise bad_request("Не удалось прочитать Excel-файл (.xlsx)") from e
    rows = iter(all_rows)
    header = [COLUMNS.get((_cell(h) or "").lower()) for h in next(rows, [])]
    if "full_name" not in header:
        raise bad_request("Нет колонки «ФИО»")
    branches = {b.name.lower(): b.id for b in await db.scalars(select(Branch).where(Branch.archived_at.is_(None)))}
    levels = {}
    for lv in await db.scalars(select(Level)):
        levels[lv.code.lower()] = lv
        levels[lv.name.lower()] = lv
    groups = {g.name.lower(): g for g in await db.scalars(select(Group).where(Group.archived_at.is_(None)))}
    allowed = actor.branches_for("students", "create")
    seen: set[str] = set()
    ok, errors = [], []
    for n, raw in enumerate(rows, start=2):
        if n - 1 > MAX_ROWS:
            errors.append({"row": n, "error": f"Не больше {MAX_ROWS} строк за раз"})
            break
        r = {f: raw[i] for i, f in enumerate(header) if f and i < len(raw)}
        if not any(_cell(v) for v in r.values()):
            continue
        try:
            name = _cell(r.get("full_name"))
            if not name or len(name) < 3:
                raise ValueError("пустое ФИО")
            phone = _phone(r.get("phone"))
            if phone and (phone in seen or await db.scalar(select(Student.id).where(Student.phone == phone,
                                                                                   Student.archived_at.is_(None)))):
                raise ValueError("ученик с этим телефоном уже есть")
            branch_id = branches.get((_cell(r.get("branch")) or "").lower())
            if branch_id is None:
                raise ValueError("неизвестный филиал")
            if allowed is not None and branch_id not in allowed:
                raise ValueError("нет доступа к филиалу")
            level = levels.get((_cell(r.get("level")) or "").lower())
            if _cell(r.get("level")) and level is None:
                raise ValueError("неизвестный уровень")
            group = groups.get((_cell(r.get("group")) or "").lower())
            if _cell(r.get("group")) and (group is None or group.branch_id != branch_id):
                raise ValueError("группа не найдена в этом филиале")
            left = int(float(_cell(r.get("lessons_left")) or 0))
            price = int(float(_cell(r.get("lesson_price")) or 0)) or (level.lesson_price if level else 0)
            parent_phone = _phone(r.get("parent_phone"))
            if parent_phone and parent_phone == phone:
                raise ValueError("телефон родителя совпадает с телефоном ученика")
            ok.append({"row": n, "full_name": name, "phone": phone, "birth_date": _date(r.get("birth_date")),
                       "branch_id": branch_id, "level_id": (group.level_id if group else None) or (level.id if level else None),
                       "group_id": group.id if group else None, "lessons_left": left, "lesson_price": price,
                       "parent_name": _cell(r.get("parent_name")), "parent_phone": parent_phone,
                       "relation": _cell(r.get("relation"))})
            if phone:
                seen.add(phone)
        except ValueError as e:
            errors.append({"row": n, "error": str(e)})
    return ok, errors


@router.post("/import/students")
async def import_students(db: DB, actor: Actor = require("students", "create"), file: UploadFile = File(...),
                          commit: bool = Query(False)) -> dict:
    limit = get_settings().import_max_mb * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise bad_request(f"Файл больше {get_settings().import_max_mb} МБ")
    ok, errors = await _parse(db, data, actor)
    if not commit:
        return {"preview": [{k: (v.isoformat() if isinstance(v, date) else v) for k, v in r.items()} for r in ok[:50]],
                "valid": len(ok), "errors": errors}
    if errors:
        raise bad_request(f"Исправьте ошибки в файле: {len(errors)} строк")
    if any(r["lessons_left"] for r in ok) and not actor.can("payments", "create"):
        raise forbidden("Остатки уроков переносит сотрудник с правом приёма оплат")
    created = 0
    for r in ok:
        s = Student(full_name=r["full_name"], phone=r["phone"], birth_date=r["birth_date"], branch_id=r["branch_id"],
                    level_id=r["level_id"], status=StudentStatus.ACTIVE, source="import", balance_lesson_price=r["lesson_price"])
        db.add(s)
        await db.flush()
        if r["phone"]:
            s.user_id = (await upsert_portal_user(db, r["phone"], r["full_name"], UserKind.STUDENT)).id
        if r["parent_phone"]:
            await add_guardian(db, s, GuardianIn(full_name=r["parent_name"] or "Родитель", phone=r["parent_phone"],
                                                 relation=r["relation"]))
        if r["lessons_left"]:
            await bal.apply(db, s, "manual", lessons=r["lessons_left"], price=r["lesson_price"], actor_id=actor.id,
                            note="Остаток при переносе из таблицы")
            await write_audit(db, actor_id=actor.id, action="student.import_balance", entity="student", entity_id=s.id,
                              branch_id=s.branch_id, ip=actor.ip, after={"lessons": r["lessons_left"], "price": r["lesson_price"]})
        if r["group_id"]:
            g = await db.get(Group, r["group_id"])
            cnt = await db.scalar(select(func.count()).select_from(GroupMember).where(GroupMember.group_id == g.id,
                                                                                        GroupMember.left_on.is_(None)))
            if cnt < g.capacity:
                db.add(GroupMember(group_id=g.id, student_id=s.id, joined_on=today()))
                await chats.sync_student_in_group_chat(db, g, s, True)
        created += 1
    await write_audit(db, actor_id=actor.id, action="student.import", entity="student", ip=actor.ip,
                      note=f"{created} учеников из «{(file.filename or '')[:80]}»")
    await db.commit()
    return {"created": created}


@router.get("/import/students/template.xlsx")
async def template(actor: Actor = require("students", "create")):
    from app.modules.finance.router import _xlsx

    return _xlsx("Ученики", ["ФИО", "Телефон", "Дата рождения", "Филиал", "Уровень", "Группа", "Осталось уроков", "Цена урока",
                             "ФИО родителя", "Телефон родителя", "Кем приходится"],
                 [["Алия Нурланова", "+77051112233", "12.03.2014", "Янги шахар", "ELE", "", 6, 3000, "Сауле Нурланова",
                   "+77051112299", "мама"]], "students-template.xlsx")
