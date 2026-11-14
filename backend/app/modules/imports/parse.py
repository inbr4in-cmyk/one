"""Reading the old CRM's exports: XLSX/CSV → rows, header detection, file kind detection, one parser per kind.

Everything here is pure CPU work on bytes: no database, no I/O. The router runs it in a worker thread.
Files are read with openpyxl (read_only, data_only: formulas are never evaluated) or the csv module; nothing in a file
is ever executed.
"""

import csv
import hashlib
import io
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any, Callable

from app.core.security import normalize_phone

MAX_ROWS = 50_000  # non-empty rows per file; the biggest real export has ~4 200
MAX_COLS = 64


# ---------- reading ----------
def _decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "cp1251"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ValueError("Не удалось прочитать CSV: кодировка не UTF-8 и не Windows-1251")


def read_rows(data: bytes, filename: str) -> list[tuple[int, tuple]]:
    """Non-empty rows as (1-based row number, cells). Trailing empty cells are kept; the sheet's formatting-only rows
    (exports pad to 10× the data with empty rows) are dropped."""
    name = (filename or "").lower()
    out: list[tuple[int, tuple]] = []
    if name.endswith(".csv") or not data[:2] == b"PK":
        if name.endswith((".xlsx", ".xlsm")):
            raise ValueError("Файл повреждён или это не Excel (.xlsx)")
        text = _decode(data)
        first = text.split("\n", 3)[:3]
        delim = ";" if sum(x.count(";") for x in first) >= sum(x.count(",") for x in first) else ","
        for n, row in enumerate(csv.reader(io.StringIO(text), delimiter=delim), start=1):
            cells = tuple(c.strip() if isinstance(c, str) else c for c in row[:MAX_COLS])
            if any(c not in (None, "") for c in cells):
                out.append((n, cells))
                if len(out) > MAX_ROWS:
                    raise ValueError(f"Больше {MAX_ROWS} строк в одном файле")
        return out
    from openpyxl import load_workbook

    try:
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as e:  # noqa: BLE001 — a broken file is the user's error
        raise ValueError("Не удалось прочитать Excel-файл (.xlsx)") from e
    try:
        ws = next((w for w in wb.worksheets if w.max_row and w.max_row > 1), wb.worksheets[0])
        for n, row in enumerate(ws.iter_rows(values_only=True), start=1):
            cells = tuple(row[:MAX_COLS])
            if any(c not in (None, "") for c in cells):
                out.append((n, cells))
                if len(out) > MAX_ROWS:
                    raise ValueError(f"Больше {MAX_ROWS} строк в одном файле")
        return out
    finally:
        wb.close()


# ---------- small value helpers ----------
_HOMO = str.maketrans({"a": "а", "b": "в", "c": "с", "e": "е", "h": "н", "k": "к", "m": "м", "o": "о", "p": "р", "t": "т",
                       "x": "х", "y": "у"})


def cell(v: Any) -> str | None:
    if v is None:
        return None
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    s = str(v).replace("\xa0", " ").strip()
    return s or None


def norm(v: Any) -> str:
    """Comparison key for names: lower case, ё→е, single spaces."""
    s = cell(v) or ""
    return re.sub(r"\s+", " ", s.lower().replace("ё", "е")).strip()


def group_key(v: Any) -> str:
    """«834-B» (Latin B) and «834-В» (Cyrillic В) are the same group in the old CRM; spaces don't matter."""
    s = norm(v)
    s = re.sub(r"^(группа|гр\.)\s+", "", s)
    return re.sub(r"\s*-\s*", "-", s).translate(_HOMO).replace(" ", "")


def compact(v: Any) -> str:
    return re.sub(r"[\s\-_.]+", "", norm(v))


def empty_marker(v: Any) -> bool:
    s = cell(v)
    return s is None or s in ("[Нет]", "---", "-", "—")


def phone(v: Any) -> str | None:
    """+7XXXXXXXXXX or None. Numbers come as ints (87011234567), «8 701 123 4567», «+77011234567», 10 digits."""
    s = cell(v)
    if not s:
        return None
    p = normalize_phone(s)
    return p if len(p) == 12 and p.startswith("+7") else None


def to_date(v: Any) -> date | None:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = cell(v)
    if not s or empty_marker(s):
        return None
    s = s.split()[0]
    for fmt in ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def day_month(s: str, today: date, year: int | None = None) -> date | None:
    """«07.09» → the latest such date not too far in the future (the exports omit the year); «18.11.25» → as written."""
    m = re.match(r"(\d{1,2})\.(\d{1,2})(?:\.(\d{2,4}))?$", s.strip())
    if not m:
        return None
    d, mo = int(m.group(1)), int(m.group(2))
    y = int(m.group(3)) if m.group(3) else year
    if y is not None and y < 100:
        y += 2000
    try:
        if y is not None:
            return date(y, mo, d)
        guess = date(today.year, mo, d)
        return guess if guess <= today + timedelta(days=60) else date(today.year - 1, mo, d)
    except ValueError:
        return None


def to_time(v: Any) -> time | None:
    if isinstance(v, time):
        return v
    if isinstance(v, datetime):
        return v.time()
    s = cell(v)
    m = re.match(r"(\d{1,2})[:.](\d{2})", s or "")
    if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
        return None
    return time(int(m.group(1)), int(m.group(2)))


def money(v: Any) -> int | None:
    """Integer tenge, half up. The old CRM keeps tiyn (95 042 143,51); our money is whole tenge."""
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        x = float(v)
    else:
        s = re.sub(r"[\s\xa0₸тг.]+$", "", str(v)).replace("\xa0", "").replace(" ", "").replace(",", ".")
        try:
            x = float(s)
        except ValueError:
            return None
    return int(x + 0.5) if x >= 0 else -int(-x + 0.5)


def number(v: Any) -> int | None:
    m = money(v)
    return m


WEEKDAYS = {"пн": 0, "вт": 1, "ср": 2, "чт": 3, "пт": 4, "сб": 5, "вс": 6}
DAY_NAMES = {"понедельник": 0, "вторник": 1, "среда": 2, "четверг": 3, "пятница": 4, "суббота": 5, "воскресенье": 6}


def weekdays(v: Any) -> list[int]:
    return sorted({WEEKDAYS[p] for p in re.split(r"[/,\s]+", norm(v)) if p in WEEKDAYS})


def fingerprint(row: dict) -> str:
    payload = json.dumps({k: v for k, v in row.items() if k != "row"}, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()[:40]


def person_words(v: Any) -> list[str]:
    return [w for w in norm(v).replace(",", " ").split(" ") if w]


def short_key(words: list[str]) -> str | None:
    """«Иванова Анна Петровна» / «Иванова А.» / «Иванова А. П.» → «иванова|а»: surname + first initial."""
    words = [w for w in words if w not in ("с",)]
    if len(words) < 2:
        return None
    return f"{words[0]}|{words[1][0]}"


_SINCE = re.compile(r"^с\s+\d{1,2}\.\d{1,2}(?:\.\d{2,4})?\s+", re.I)
_SINCE_ANY = re.compile(r"(?:^|\s)с\s+\d{1,2}\.\d{1,2}(?:\.\d{2,4})?\s+", re.I)


def current_people(v: Any) -> list[str]:
    """«с 18.11.25 Иванова Анна\\nс 09.06 Петрова Дана» → the latest line's person (the teacher now);
    «Иванова А., Петрова Д.» → both, in order."""
    s = cell(v)
    if not s or empty_marker(s):
        return []
    lines = [x.strip() for x in s.split("\n") if x.strip()]
    dated = [x for x in lines if _SINCE.match(x)]
    last = dated[-1] if dated else s
    # «с 02.09 Анна Б. В. с 01.10 Дана Е.» on one line
    parts = [p.strip() for p in _SINCE_ANY.split(last) if p.strip()]
    if dated or len(parts) > 1:
        return parts[-1:]
    out = []
    for chunk in re.split(r"[,\n]", s):
        chunk = chunk.strip()
        if chunk:
            out.append(chunk)
    return out


# ---------- kinds ----------
@dataclass
class Parsed:
    kind: str
    rows: list[dict] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)  # {"row", "reason"} — rows we could not even read
    info: dict = field(default_factory=dict)


@dataclass
class Kind:
    code: str
    title: str
    order: int
    headers: tuple[str, ...] = ()  # signature for detection; non-tabular kinds use `marker`
    marker: str | None = None
    parse: Callable[[list[tuple[int, tuple]], int, date], Parsed] | None = None


def _hmap(header: tuple) -> dict[str, int]:
    out: dict[str, int] = {}
    for i, h in enumerate(header):
        k = norm(h)
        if k and k not in out:
            out[k] = i
    return out


def _getter(header: tuple):
    hm = _hmap(header)

    def get(cells: tuple, name: str):
        i = hm.get(name)
        return cells[i] if i is not None and i < len(cells) else None

    return get


def _tabular(rows, hdr):
    header = rows[hdr][1]
    return _getter(header), rows[hdr + 1:]


def parse_teachers(rows, hdr, today) -> Parsed:
    get, data = _tabular(rows, hdr)
    out = Parsed("teachers")
    for n, c in data:
        name = cell(get(c, "фио"))
        if not name:
            continue
        out.rows.append({
            "row": n, "full_name": re.sub(r"\s+", " ", name),
            "branches": [x.strip() for x in (cell(get(c, "филиалы")) or "").split("\n") if x.strip() and not empty_marker(x)],
            "levels": [x.strip() for x in (cell(get(c, "уровни")) or "").split("\n") if x.strip() and not empty_marker(x)],
            "disciplines": [x.strip() for x in (cell(get(c, "языки")) or "").split("\n") if x.strip()],
            "birth_date": to_date(get(c, "дата рождения")), "since": to_date(get(c, "работает с")),
        })
    return out


def _group_rows(rows, hdr, today, kind="groups") -> Parsed:
    header = rows[hdr][1]
    get = _getter(header)
    hm = _hmap(header)
    si = hm.get("расписание")
    out = Parsed(kind)
    for n, c in rows[hdr + 1:]:
        name = cell(get(c, "группа"))
        if not name:
            continue
        # «Расписание» spans three columns: days, start time, end time (the two after it have no header)
        days = weekdays(c[si]) if si is not None and si < len(c) else []
        start = to_time(c[si + 1]) if si is not None and si + 1 < len(c) else None
        end = to_time(c[si + 2]) if si is not None and si + 2 < len(c) else None
        if start is None and si is not None and si < len(c):
            m = re.search(r"(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})", cell(c[si]) or "")
            if m:
                start, end = to_time(m.group(1)), to_time(m.group(2))
        out.rows.append({
            "row": n, "name": re.sub(r"\s+", " ", name).strip(), "key": group_key(name), "status": cell(get(c, "статус")),
            "weekdays": days, "start": start, "end": end, "opened": to_date(get(c, "дата открытия")),
            "closed": to_date(get(c, "дата окончания")), "teachers": current_people(get(c, "преподаватели")),
            "room": None if empty_marker(get(c, "аудитория")) else cell(get(c, "аудитория")),
        })
    return out


def parse_groups(rows, hdr, today) -> Parsed:
    return _group_rows(rows, hdr, today)


_SCHED = re.compile(r"(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})\s+([А-Яа-я/]+)\s*\(?\s*с\s+(\d{1,2}\.\d{1,2}(?:\.\d{2,4})?)?")


def schedule_entries(v: Any, today: date) -> list[dict]:
    """«18:00-19:00 Пн/Ср/Пт\\n(с 07.09)\\n13:00-14:00 Сб\\n(с 09.10)» → [{start, end, weekdays, since}, …]; «+ ещё 1»
    means the export cut the list (the room schedule has the rest)."""
    s = (cell(v) or "").replace("\n", " ")
    out = []
    for m in _SCHED.finditer(s):
        out.append({"start": to_time(m.group(1)), "end": to_time(m.group(2)), "weekdays": weekdays(m.group(3)),
                    "since": day_month(m.group(4), today) if m.group(4) else None})
    return out


def parse_individual(rows, hdr, today) -> Parsed:
    get, data = _tabular(rows, hdr)
    out = Parsed("individual")
    for n, c in data:
        name = cell(get(c, "фио"))
        if not name:
            continue
        out.rows.append({
            "row": n, "ext_id": cell(get(c, "id")), "short_name": re.sub(r"\s+", " ", name), "branch": cell(get(c, "филиал")),
            "discipline": cell(get(c, "дисциплина")), "level": None if empty_marker(get(c, "уровень")) else cell(get(c, "уровень")),
            "start": to_date(get(c, "дата старта")), "end": to_date(get(c, "дата окончания")),
            "schedule": schedule_entries(get(c, "расписание"), today), "cut": "ещё" in (cell(get(c, "расписание")) or ""),
            "teachers": current_people(get(c, "преподаватели")),
            "room": None if empty_marker(get(c, "аудитория")) else cell(get(c, "аудитория")),
            "debt": cell(get(c, "долг, часы")), "note": cell(get(c, "описание")),
        })
    return out


_CONTACT_A = re.compile(r"([^()\n,;]*?)\s*\(\s*(?:тел|моб|раб|дом)\.?\s*:?\s*([+\d][\d\s\-]{8,}?)\s*\)", re.I)
_CONTACT_B = re.compile(r"([+\d][\d\s\-]{8,}\d)\s*\(([^)]*)\)")
_GROUP_IN_LIST = re.compile(r"Группа\s+([^,]+?)(?=,|$)")


def contacts(v: Any) -> list[dict]:
    s = cell(v) or ""
    out, seen = [], set()
    for rel, ph in _CONTACT_A.findall(s):
        p = phone(ph)
        if p and p not in seen:
            seen.add(p)
            out.append({"relation": rel.strip(" ,.;") or None, "phone": p})
    for ph, rel in _CONTACT_B.findall(s):
        p = phone(ph)
        if p and p not in seen:
            seen.add(p)
            out.append({"relation": rel.strip(" ,.;") or None, "phone": p})
    return out


def parse_students(rows, hdr, today) -> Parsed:
    get, data = _tabular(rows, hdr)
    out = Parsed("students")
    for n, c in data:
        cid = cell(get(c, "ид клиента"))
        surname, first, middle = (None if empty_marker(get(c, k)) else cell(get(c, k)) for k in ("фамилия", "имя", "отчество"))
        if not (cid or surname or first):
            continue
        groups_raw = cell(get(c, "группы")) or ""
        mob, tel = phone(get(c, "моб. телефон")), phone(get(c, "телефон"))
        raw_phone = cell(get(c, "моб. телефон")) or cell(get(c, "телефон"))
        out.rows.append({
            "row": n, "client_id": cid, "crm_id": cell(get(c, "ид")),
            "branch": None if empty_marker(get(c, "филиалы")) else cell(get(c, "филиалы")),
            "surname": surname, "first_name": first, "middle_name": middle,
            "full_name": " ".join(x for x in (surname, first, middle) if x),
            "birth_date": to_date(get(c, "дата рождения")),
            "level": None if empty_marker(get(c, "уровни")) else cell(get(c, "уровни")),
            "phone": mob or tel, "bad_phone": raw_phone if raw_phone and not (mob or tel) else None,
            "email": cell(get(c, "email")), "contacts": contacts(get(c, "конт. лица")),
            "status": cell(get(c, "статус")),
            "groups": [group_key(g) for g in _GROUP_IN_LIST.findall(groups_raw)],
            "group_names": [g.strip() for g in _GROUP_IN_LIST.findall(groups_raw)],
            "other_groups": [g.strip() for g in groups_raw.split(",") if g.strip() and not g.strip().startswith("Группа")]
            if "Индивидуально" in groups_raw or "Мини-группа" in groups_raw else [],
            "income": get(c, "приход"), "expense": get(c, "расход"),
            "note": cell(get(c, "описание")), "applied_on": to_date(get(c, "дата обращения")),
        })
    return out


def parse_payments(rows, hdr, today) -> Parsed:
    get, data = _tabular(rows, hdr)
    out = Parsed("payments")
    for n, c in data:
        branch = cell(get(c, "филиал"))
        if branch and branch.startswith("Всего найдено"):
            out.info["footer"] = branch
            continue
        inv, cid = cell(get(c, "счёт")) or cell(get(c, "счет")), cell(get(c, "ид клиента"))
        if not (inv or cid):
            continue
        amount_raw = get(c, "размер оплаты")
        out.rows.append({
            "row": n, "branch": branch, "invoice": inv, "client_id": cid, "payer": cell(get(c, "плательщик")),
            "created": to_date(get(c, "дата создания")), "paid_on": to_date(get(c, "дата оплаты")),
            "amount": money(amount_raw), "amount_exact": float(amount_raw) if isinstance(amount_raw, (int, float)) else None,
            "purpose": cell(get(c, "назначение")), "method": cell(get(c, "способ оплаты")), "state": cell(get(c, "состояние")),
            "received_by": cell(get(c, "кто принял")), "comment": cell(get(c, "комментарий")),
        })
    return out


def parse_library(rows, hdr, today) -> Parsed:
    get, data = _tabular(rows, hdr)
    out = Parsed("library")
    for n, c in data:
        title = cell(get(c, "наименование"))
        if not title:
            continue
        out.rows.append({
            "row": n, "title": title, "price": money(get(c, "цена")) or 0,
            "for_lend": number(get(c, "для выдачи")) or 0, "for_sale": number(get(c, "для продажи")) or 0,
            "lent": number(get(c, "выдано")) or 0, "sold": number(get(c, "продано")) or 0,
            "created": to_date(get(c, "дата создания")),
        })
    return out


def parse_communications(rows, hdr, today) -> Parsed:
    get, data = _tabular(rows, hdr)
    out = Parsed("communications")
    for n, c in data:
        student, text = cell(get(c, "ученик")), cell(get(c, "описание"))
        if not (student or text):
            continue
        raw = cell(get(c, "дата")) or ""
        parts = raw.split()
        at = None
        if parts:
            d = to_date(parts[0])
            t = to_time(parts[1]) if len(parts) > 1 else None
            if d:
                at = datetime.combine(d, t or time(12, 0))
        out.rows.append({
            "row": n, "at": at, "student": student, "student_id": cell(get(c, "ид ученика")), "who": cell(get(c, "кто контактировал")),
            "channel": cell(get(c, "способ")), "direction": cell(get(c, "направление")), "phone": phone(get(c, "телефон")),
            "text": text,
        })
    return out


def parse_unsupported(kind: str):
    def parse(rows, hdr, today) -> Parsed:
        out = Parsed(kind)
        for n, c in rows[hdr + 1:]:
            if any(cell(x) for x in c):
                out.rows.append({"row": n, "values": [cell(x) for x in c[:10]]})
        return out

    return parse


def parse_attendance(rows, hdr, today) -> Parsed:
    """«Карта посещаемости»: one block per group or individual student.

    <group name or student «Фамилия И.»>
    Филиал/Компания: | <branch>;  Дисциплина: | …;  Уровень: | <level>;  Преподаватели: | <short names>
    Ученик | … | 02.11 | 04.11 | … | Занятий | …
    <student «Фамилия Имя»> | … | ✓ | × | …
    Итого посещений | … (groups only)
    """
    out = Parsed("attendance")
    title = cell(rows[0][1][0]) if rows else ""
    m = re.search(r"(\d{2})\.(\d{2})\.(\d{2,4})\s*-\s*(\d{2})\.(\d{2})\.(\d{2,4})", title or "")
    year = (int(m.group(3)) + (2000 if len(m.group(3)) == 2 else 0)) if m else today.year
    out.info["period"] = title
    i = 0
    while i < len(rows):
        n, c = rows[i]
        nxt = rows[i + 1][1] if i + 1 < len(rows) else ()
        if cell(c[0]) and nxt and norm(nxt[0]) == "филиал/компания:":
            block = {"label": cell(c[0]).strip(), "row": n}
            j = i + 1
            while j < len(rows) and norm(rows[j][1][0]).endswith(":") and norm(rows[j][1][0]) != "итого:":
                k = norm(rows[j][1][0]).rstrip(":")
                v = cell(rows[j][1][1]) if len(rows[j][1]) > 1 else None
                block[{"филиал/компания": "branch", "дисциплина": "discipline", "уровень": "level",
                       "преподаватели": "teachers"}.get(k, k)] = v
                j += 1
            dates: dict[int, date] = {}
            if j < len(rows) and norm(rows[j][1][0]) == "ученик":
                for ci, v in enumerate(rows[j][1]):
                    d = day_month(cell(v) or "", today, year) if ci > 0 and isinstance(v, str) and re.match(r"\d{1,2}\.\d{1,2}$", v.strip()) else None
                    if d:
                        dates[ci] = d
                j += 1
            while j < len(rows):
                rn, rc = rows[j]
                first = cell(rc[0])
                nxt2 = rows[j + 1][1] if j + 1 < len(rows) else ()
                if not first or norm(first).startswith("итого") or (nxt2 and norm(nxt2[0]) == "филиал/компания:") \
                        or norm(first).endswith(":"):
                    break
                marks = {}
                for ci, d in dates.items():
                    v = cell(rc[ci]) if ci < len(rc) else None
                    if v in ("✓", "✔", "+", "П", "п"):
                        marks[d] = "present"
                    elif v in ("×", "✕", "x", "х", "Н", "н", "-"):
                        marks[d] = "absent"
                out.rows.append({"row": rn, "block": block["label"], "block_row": block["row"], "branch": block.get("branch"),
                                 "level": block.get("level"), "discipline": block.get("discipline"),
                                 "teachers": current_people(block.get("teachers")), "student": re.sub(r"\s+", " ", first),
                                 "marks": {d.isoformat(): s for d, s in sorted(marks.items())}})
                j += 1
            i = j
            continue
        i += 1
    return out


def parse_room_schedule(rows, hdr, today) -> Parsed:
    """«Расписание аудиторий»: a day header row (Понедельник …), then one or more rows per room; each cell is
    «Teacher\\nGroup or student\\nBranch\\nHH:MM-HH:MM\\nс DD.MM (Пн/Ср/Пт)»."""
    out = Parsed("schedule")
    title = cell(rows[0][1][0]) if rows else ""
    out.info["period"] = title
    day = None
    room = None
    for n, c in rows:
        first = cell(c[0])
        if first == "#" or (first and first.startswith("Расписание")):
            continue
        second = cell(c[1]) if len(c) > 1 else None
        if not first and second and norm(second) in DAY_NAMES:
            day = DAY_NAMES[norm(second)]
            continue
        if first:
            room = first
        for ci, v in enumerate(c[1:], start=1):
            s = cell(v)
            if not s or "\n" not in s:
                continue
            parts = [p.strip() for p in s.split("\n")]
            while len(parts) < 5:
                parts.append("")
            tm = re.match(r"(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})", parts[3])
            since = re.match(r"с\s+(\d{1,2}\.\d{1,2}(?:\.\d{2,4})?)\s*\(([^)]*)\)", parts[4])
            out.rows.append({
                "row": n, "col": ci, "day": day, "room": room, "teacher": parts[0], "who": parts[1], "branch": parts[2],
                "start": to_time(tm.group(1)) if tm else None, "end": to_time(tm.group(2)) if tm else None,
                "since": day_month(since.group(1), today) if since else None,
                "weekdays": weekdays(since.group(2)) if since else ([day] if day is not None else []),
            })
    return out


KINDS: dict[str, Kind] = {k.code: k for k in [
    Kind("teachers", "Преподаватели", 10, ("фио", "языки", "уровни", "категории", "филиалы", "работает с"), parse=parse_teachers),
    Kind("groups", "Группы", 20, ("группа", "статус", "ак. часов", "расписание", "дата открытия", "аудитория"), parse=parse_groups),
    Kind("students", "Ученики", 30, ("ид клиента", "фамилия", "имя", "отчество", "филиалы", "конт. лица", "приход", "расход"),
         parse=parse_students),
    Kind("individual", "Индивидуальные занятия", 40, ("id", "фио", "ак. часов", "дата старта", "расписание", "долг, часы"),
         parse=parse_individual),
    Kind("schedule", "Расписание аудиторий", 50, marker="расписание аудиторий", parse=parse_room_schedule),
    Kind("attendance", "Посещаемость", 60, marker="карта посещаемости", parse=parse_attendance),
    Kind("payments", "Платежи", 70, ("плательщик", "размер оплаты", "назначение", "способ оплаты", "счёт", "состояние"),
         parse=parse_payments),
    Kind("library", "Книги", 80, ("наименование", "выдаётся", "продаётся", "для выдачи", "для продажи", "продано"),
         parse=parse_library),
    Kind("communications", "Коммуникации", 90, ("дата", "ученик", "кто контактировал", "способ", "направление", "длительность"),
         parse=parse_communications),
    Kind("test_results", "Результаты тестов", 100, ("дата", "ученик", "тест", "результат теста", "результат теста, %"),
         parse=parse_unsupported("test_results")),
    Kind("homework_plans", "Домашние задания / планы", 110, ("сотрудник", "учебная единица", "занятие", "отображать в лк"),
         parse=parse_unsupported("homework_plans")),
]}


def detect(rows: list[tuple[int, tuple]]) -> tuple[str | None, int, float]:
    """(kind, header row index into `rows`, confidence 0..1). Looks at the first 10 rows: the export title comes first."""
    head = rows[:10]
    for k in KINDS.values():
        if k.marker and head and norm(head[0][1][0]).startswith(k.marker):
            return k.code, 0, 1.0
    best: tuple[str | None, int, float] = (None, 0, 0.0)
    for idx, (_, cells) in enumerate(head):
        names = {norm(x) for x in cells if cell(x)}
        for k in KINDS.values():
            if not k.headers:
                continue
            score = len(names & set(k.headers)) / len(k.headers)
            if score > best[2]:
                best = (k.code, idx, score)
    if best[2] < 0.5:
        # Layout markers without the title row (someone deleted it)
        for idx, (_, cells) in enumerate(rows[:40]):
            if norm(cells[0]) == "филиал/компания:":
                return "attendance", 0, 0.6
            if len(cells) > 1 and norm(cells[1]) in DAY_NAMES and not cell(cells[0]):
                return "schedule", 0, 0.6
        return None, 0, best[2]
    return best


def header_for(rows: list[tuple[int, tuple]], kind: str) -> int:
    k = KINDS[kind]
    if not k.headers:
        return 0
    best, idx = -1.0, 0
    for i, (_, cells) in enumerate(rows[:10]):
        names = {norm(x) for x in cells if cell(x)}
        score = len(names & set(k.headers)) / len(k.headers)
        if score > best:
            best, idx = score, i
    return idx


def parse_file(data: bytes, filename: str, override: str | None, today: date) -> dict:
    """→ {"filename", "kind", "detected", "confidence", "header_row", "parsed": Parsed | None, "error": str | None}"""
    res: dict = {"filename": filename, "kind": None, "detected": None, "confidence": 0.0, "header_row": None,
                 "parsed": None, "error": None}
    try:
        rows = read_rows(data, filename)
    except ValueError as e:
        res["error"] = str(e)
        return res
    if not rows:
        res["error"] = "Файл пустой"
        return res
    detected, hdr, conf = detect(rows)
    res.update(detected=detected, confidence=round(conf, 2))
    kind = override or detected
    if kind is None:
        res["error"] = "Не удалось определить тип файла — выберите его вручную"
        return res
    if kind not in KINDS:
        res["error"] = "Неизвестный тип файла"
        return res
    if kind != detected:
        hdr = header_for(rows, kind)
    res["kind"] = kind
    res["header_row"] = rows[hdr][0] if KINDS[kind].headers else None
    res["parsed"] = KINDS[kind].parse(rows, hdr, today)
    return res
