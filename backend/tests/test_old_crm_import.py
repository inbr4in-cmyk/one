"""Import from the old CRM. Every file here is synthetic and built in the test, with the same layout as the real exports
(title row, header row, the same column names, ✓/× marks, «Фамилия И.» short names). No real data."""

import csv
import io
import json
from datetime import date, time, timedelta

from openpyxl import Workbook
from sqlalchemy import func, select

from app.models import (
    Accrual,
    Attendance,
    Book,
    BookStock,
    CoinEntry,
    Group,
    GroupMember,
    ImportRef,
    Lead,
    Lesson,
    Notification,
    OutboundMessage,
    Payment,
    ScheduleRule,
    Student,
    StudentGuardian,
    User,
)
from app.modules.imports.parse import current_people, detect, group_key, money, parse_file, phone, read_rows
from app.services.clock import today
from tests.conftest import branch_id, login, make_staff

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
D = today()
PAST = D - timedelta(days=2)  # a day with marks in the attendance map
FUTURE = D + timedelta(days=3)


def xlsx(rows: list[list]) -> bytes:
    wb = Workbook()
    ws = wb.active
    for r in rows:
        ws.append(r)
    # The real exports pad the sheet with formatting-only rows
    for _ in range(30):
        ws.append([None] * 5)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def csv_bytes(rows: list[list], encoding: str = "utf-8-sig") -> bytes:
    buf = io.StringIO()
    csv.writer(buf, delimiter=";").writerows(rows)
    return buf.getvalue().encode(encoding)


def dm(d: date) -> str:
    return f"{d:%d.%m}"


def files() -> dict[str, bytes]:
    teachers = xlsx([
        ["Преподаватели"],
        ["ФИО", "Языки", "Уровни", "Категории", "Филиалы", "Рейтинг", "Дата рождения", "Работает с", "Описание"],
        ["Тестова Айгуль Маратовна", "Уровни английского языка", "Elementery\nStarter", "Взрослые", "Янги Шахар", 0, None, "01.09.2025", None],
        ["Пробный Ерлан Серикович", "Уровни английского языка\nIelts", "Beginner", None, "Север", 0, None, "02.09.2025", None],
    ])
    groups = xlsx([
        ["Найденные группы"],
        ["Группа", "Статус", "Ак. часов", "Расписание", None, None, "Дата открытия", "Дата окончания", "Преподаватели", "Аудитория"],
        ["901-В", "В работе", "---", "Пн/Ср/Пт", time(16, 30), time(17, 50), "01.09.2026", None,
         "с 01.09.25 Пробный Ерлан Серикович\nс 01.10 Тестова Айгуль Маратовна", "room 3"],
        # Latin «B» in the same group name elsewhere in the old CRM
        ["902-S", "В работе", "---", "Вт/Чт/Сб", time(15, 0), time(16, 20), "02.09.2026", None, "Пробный Ерлан Серикович", "room 2"],
    ])
    groups_reserve = xlsx([
        ["Найденные группы"],
        ["Группа", "Статус", "Ак. часов", "Расписание", None, None, "Дата открытия", "Дата окончания", "Преподаватели", "Аудитория"],
        ["901-B", "Сбор резервов", "0 зан 60", None, None, None, None, None, None, None],
        ["999-S", "Сбор резервов", "0 зан 60", None, None, None, None, None, None, None],
    ])
    students = xlsx([
        ["Ученики"],
        ["ИД", "ИД клиента", "Филиалы", "Фамилия", "Имя", "Отчество", "Пол", "Возраст", "Дата рождения", "Категория", "Тип", "Дисциплины",
         "Уровни", "Цель обучения", "Email", "Телефон", "Моб. телефон", "Соц. сеть", "Адрес", "Конт. лица", "Статус", "Ответственный",
         "Группы", "Рекламный источник", "Дата обращения", "Тип обращения", "Дата визита", "Приход", "Расход", "Пользовательские поля",
         "Описание"],
        [11, 101, "Янги Шахар", "Учебная", "Алия", None, "Ж", 12, "05.06.2014", "Школьники", "Общий", "Уровни английского языка",
         "Elementery", None, None, None, 87050000001, None, None, "мама (моб.: 8 705 000 0091)", "Занимается", "Менеджер А.",
         "Группа 901-В", None, "01.09.2026", None, None, 61000, 30000, None, None],
        [12, 102, "Север", "Примерный", "Арман", None, "М", 15, "01.01.2011", "Школьники", "Общий", "Уровни английского языка",
         "Beginner", None, None, None, "+77050000002", None, None, "(моб.: +77050000092)", "Занимается", "Менеджер А.",
         "Группа 902-S, Индивидуально с Пробный Е.", None, "02.09.2026", None, None, 30000, 30000, None, None],
        [13, 103, "Янги Шахар", "Бывшая", "Дана", None, "Ж", 20, None, "Взрослые", "Общий", "Уровни английского языка",
         "Starter", None, None, None, 87050000003, None, None, "мама (моб.: 87050000093)", "Закончил обучение", "Менеджер А.",
         "Группа 901-В", None, "01.03.2026", None, None, 25000.5, 20000, None, None],
    ])
    individual = csv_bytes([
        ["Индивидуальные"],
        ["ID", "ФИО", "Филиал", "Дисциплина", "Уровень", "Категория", "Ответственный", "Ак. часов", "Тип", "Дата старта", "Дата окончания",
         "Расписание", "Преподаватели", "Аудитория", "Долг, часы", "Пользовательские поля", "Описание"],
        ["501", "Примерный А.", "Север", "Уровни английского языка", "Beginner", "", "[Нет]", "", "Общий", "07.09.2026", "",
         "18:00-19:00 Пн/Ср/Пт\n(с 07.09)\n+ ещё 1", "с 07.09 Тестова Айгуль Маратовна с 01.10 Пробный Ерлан Серикович", "room 4",
         "26 зан 60", "", ""],
    ], encoding="cp1251")
    attendance = xlsx([
        [f"Карта посещаемости ({PAST:%d.%m.%y}-{FUTURE:%d.%m.%y})"],
        ["901-В"],
        ["Филиал/Компания:", "Янги Шахар"],
        ["Дисциплина:", "Уровни английского языка"],
        ["Уровень:", "Elementery"],
        ["Преподаватели:", "Тестова А. М."],
        ["Ученик"] + [None] * 12 + [dm(PAST), dm(FUTURE), "Занятий"],
        ["Учебная Алия"] + [None] * 12 + ["✓", "×", "1/2"],
        ["Итого посещений"] + [None] * 12 + [1, 0],
        ["Примерный А."],
        ["Филиал/Компания:", "Север"],
        ["Дисциплина:", "Уровни английского языка"],
        ["Уровень:", "Beginner"],
        ["Преподаватели:", "Пробный Е. С."],
        ["Ученик"] + [None] * 12 + [dm(PAST), "Занятий"],
        ["Примерный Арман"] + [None] * 12 + ["×", "0/1"],
        ["Итого:", "1/3 (33%)"],
    ])
    room = xlsx([
        [f"Расписание аудиторий  с {dm(D)} по {D + timedelta(days=60):%d.%m.%y}"],
        ["#", "9:00-10:00", "10:00-11:00"],
        [None, "Суббота"],
        ["room 4", "Пробный Е. С.\nПримерный А.\nСевер\n9:30-10:30\nс 01.10 (Сб)\n", None],
        ["room 2", None, "Пробный Е. С.\n902-S\nСевер\n10:00-11:20\nс 02.09 (Вт/Чт/Сб)\n"],
    ])
    payments = xlsx([
        ["Приход на личный счёт, другие платежи и выставленные счета"],
        ["Филиал", "Дата создания", "Дата оплаты", "ИД клиента", "Плательщик", "Контакты", "Рекламный источник", "Ответственные",
         "Размер оплаты", "Назначение", "Способ оплаты", "Кто добавил", "Счёт", "Состояние", "Кто принял", "Тег", "Комментарий"],
        ["Янги Шахар", "01.10.2026", "01.10.2026", 101, "Учебная Алия", "87050000001", None, "Менеджер А.", 57000, "Обучение",
         "Наличные", "Менеджер А.", 7001, "Оплачен", "Менеджер А.", None, "Оплата (счёт №7001, Группа 901-В, 12 груп зан)"],
        ["Янги Шахар", "01.10.2026", "01.10.2026", 101, "Учебная Алия", "87050000001", None, "Менеджер А.", 4000, "Учебные материалы",
         "Наличные", "Менеджер А.", 7002, "Оплачен", "Менеджер А.", None, '"Elementary"'],
        ["Север", "02.10.2026", "02.10.2026", 102, "Примерный Арман", "87050000002", None, "Менеджер А.", 30000, "Обучение",
         "Наличные", "Менеджер А.", 7003, "Оплачен", "Менеджер А.", None, "Оплата (счёт №7003, Группа 902-S, 4,07 груп зан)"],
        ["Север", "03.10.2026", None, 102, "Примерный Арман", "87050000002", None, "Менеджер А.", 30000, "Обучение",
         "Наличные", "Менеджер А.", 7004, "Не оплачен", None, None, "Оплата (счёт №7004)"],
        ["Янги Шахар", "01.03.2026", "01.03.2026", 103, "Бывшая Дана", "87050000003", None, "Менеджер А.", 25000.5, "Обучение",
         "Наличные", "Менеджер А.", 7005, "Оплачен", "Менеджер А.", None, "Оплата (счёт №7005)"],
        ["Всего найдено 5 платежей от 3 плательщиков на общую сумму 146 000,50 тг."],
    ])
    library = xlsx([
        ["Библиотека"],
        ["Наименование", "Дата создания", "Кто добавил", "Выдаётся", "Продаётся", "Цена", "Для выдачи", "Для продажи", "Выдано",
         "Продано", "Описание"],
        ["Elementary", "09.10.2025", "One E.", "Нет", "Да", 4000, 0, 30, 0, 12, None],
    ])
    comms = xlsx([
        ["Коммуникации"],
        ["Дата", "Ученик", "Кто контактировал", "Способ", "Направление", "Телефон", "Длительность", "Trunk", "Описание", "ИД ученика"],
        ["03.04.2026\n15:55", "Учебная Алия", "One English", "Сайт", "Исходящая", None, None, None, "перезвонить в 15-00", None],
        ["04.04.2026\n10:00", "Незнакомый Контакт", "One English", "Сайт", "Исходящая", None, None, None, "интересовался IELTS", None],
    ])
    tests = csv_bytes([["Результаты тестов"], ["Дата", "Ученик", "Филиал", "Дисциплина", "Категория", "Тест", "Результат теста",
                                                "Результат теста, %", "Комментарий"]])
    return {"students.xlsx": students, "payments.xlsx": payments, "teachers.xlsx": teachers, "groups_2.xlsx": groups,
            "groups_1.xlsx": groups_reserve, "individual.csv": individual, "attendance_map.xlsx": attendance, "room_schedule.xlsx": room,
            "library.xlsx": library, "communications.xlsx": comms, "test_results.csv": tests}


def upload(fs: dict[str, bytes]):
    return [("files", (n, b, XLSX if n.endswith("xlsx") else "text/csv")) for n, b in fs.items()]


async def counts(db) -> dict:
    out = {}
    for m in (Student, User, Group, GroupMember, ScheduleRule, Lesson, Attendance, Payment, Book, ImportRef, Lead, StudentGuardian):
        out[m.__name__] = await db.scalar(select(func.count()).select_from(m))
    return out


# ---------- parsing ----------
def test_parsing_helpers():
    assert phone(87011234567) == "+77011234567" and phone("8 701 123 4567") == "+77011234567" and phone("7011234567") == "+77011234567"
    assert phone("12345") is None
    assert money(25000.5) == 25001 and money("95 042 143,51") == 95042144 and money(None) is None
    assert group_key("834-B") == group_key("834-В") == group_key(" Группа 834 - в")
    assert current_people("с 18.11.25 Анна Б.\nс 09.06 Дана Е.") == ["Дана Е."]
    assert current_people("с 07.09 Анна Б. В. с 01.10 Дана Е.") == ["Дана Е."]
    assert current_people("[Нет]") == []


def test_detects_every_kind_and_header_row():
    expect = {"students.xlsx": "students", "payments.xlsx": "payments", "teachers.xlsx": "teachers", "groups_2.xlsx": "groups",
              "groups_1.xlsx": "groups", "individual.csv": "individual", "attendance_map.xlsx": "attendance",
              "room_schedule.xlsx": "schedule", "library.xlsx": "library", "communications.xlsx": "communications",
              "test_results.csv": "test_results"}
    for name, data in files().items():
        res = parse_file(data, name, None, D)
        assert res["error"] is None and res["kind"] == expect[name], (name, res["kind"], res["error"])
        if res["header_row"] is not None:
            assert res["header_row"] == 2  # the title row comes first
    rows = read_rows(files()["individual.csv"], "individual.csv")  # cp1251
    assert rows[1][1][1] == "ФИО" and detect(rows)[0] == "individual"
    hw = csv_bytes([["Домашние задания / Планы занятий"], ["Сотрудник", "Учебная единица", "Занятие", "Отображать в ЛК", "Комментарий", ""]])
    res = parse_file(hw, "hw.csv", None, D)
    assert res["kind"] == "homework_plans" and res["parsed"].rows == []
    # Override wins over detection
    assert parse_file(files()["groups_1.xlsx"], "g.xlsx", "teachers", D)["kind"] == "teachers"
    pay = parse_file(files()["payments.xlsx"], "p.xlsx", None, D)["parsed"]
    assert len(pay.rows) == 5 and pay.info["footer"].startswith("Всего найдено")


# ---------- the pipeline ----------
async def test_preview_commit_reimport(db, client, owner_h):
    y = await branch_id(db, "Янги шахар")
    fs = files()
    before = await counts(db)
    r = await client.post("/api/import/old-crm", headers=owner_h, files=upload(fs), data={"default_branch_id": str(y)})
    assert r.status_code == 200, r.text
    prev = r.json()
    assert prev["dry_run"] is True
    assert await counts(db) == before  # a preview writes nothing
    by = {f["filename"]: f for f in prev["files"]}
    assert by["students.xlsx"]["totals"]["new"] == 3 and by["teachers.xlsx"]["totals"]["new"] == 2
    # Files run in dependency order whatever the upload order
    order = [prev["files"][i]["kind"] for i in prev["order"]]
    assert order.index("teachers") < order.index("groups") < order.index("students") < order.index("individual") \
        < order.index("schedule") < order.index("attendance") < order.index("payments")
    reserve = {x["label"]: x for x in by["groups_1.xlsx"]["rows"]}
    assert reserve["Группа 901-B"]["status"] == "skip"  # same group as «901-В», Latin letter
    assert reserve["Группа 999-S"]["status"] == "error" and "преподавател" in reserve["Группа 999-S"]["reason"]
    unpaid = next(x for x in by["payments.xlsx"]["rows"] if "7004" in x["label"])
    assert unpaid["status"] == "skip"
    assert by["test_results.csv"]["totals"] == {"new": 0, "update": 0, "skip": 0, "error": 0}

    r = await client.post("/api/import/old-crm?commit=true", headers=owner_h, files=upload(fs), data={"default_branch_id": str(y)})
    assert r.status_code == 200, r.text
    done = r.json()
    assert done["totals"] == prev["totals"]  # the preview said exactly what the commit did
    after = await counts(db)

    # Teachers: no phone, no password; cannot sign in
    t = await db.scalar(select(User).where(User.full_name == "Тестова Айгуль Маратовна"))
    assert t.kind == "staff" and t.phone is None and t.password_hash is None
    # Group: teacher is the latest one in the history, branch from the room schedule / attendance, level from attendance
    g = await db.scalar(select(Group).where(Group.name == "901-В"))
    assert g.teacher_id == t.id and g.branch_id == y and g.status == "active"
    assert await db.scalar(select(func.count()).select_from(ScheduleRule).where(ScheduleRule.group_id == g.id)) == 1
    # The room schedule has 902-S at another time on the same days: the group card's time is kept, the row says why
    g2 = await db.scalar(select(Group).where(Group.name == "902-S"))
    assert await db.scalar(select(func.count()).select_from(ScheduleRule).where(ScheduleRule.group_id == g2.id)) == 1
    clash = next(x for x in by["room_schedule.xlsx"]["rows"] if x["label"].startswith("902-S"))
    assert clash["status"] == "skip" and "другое время" in clash["reason"]
    # Students: active one in the group with a parent and a portal account; finished one is not in a group
    a = await db.scalar(select(Student).where(Student.full_name == "Учебная Алия"))
    assert a.phone == "+77050000001" and a.user_id and a.status == "active" and a.source == "import"
    assert await db.scalar(select(GroupMember.id).where(GroupMember.student_id == a.id, GroupMember.group_id == g.id))
    assert await db.scalar(select(func.count()).select_from(StudentGuardian).where(StudentGuardian.student_id == a.id)) == 1
    # Opening balance: «Приход» − «Расход» − paid books (credited to the account in the old CRM, never written off)
    assert a.money_balance == 61000 - 30000 - 4000 and a.lessons_left == 0
    old = await db.scalar(select(Student).where(Student.full_name == "Бывшая Дана"))
    assert old.status == "finished" and old.user_id is None and old.money_balance == 5001
    assert not await db.scalar(select(GroupMember.id).where(GroupMember.student_id == old.id))
    assert "87050000093" not in (old.notes or "") and "+77050000093" in (old.notes or "")
    # Individual lessons: a one-student group with the student, the rule from the CSV and the extra one from the room schedule
    arman = await db.scalar(select(Student).where(Student.full_name == "Примерный Арман"))
    ind = await db.scalar(select(Group).join(GroupMember, GroupMember.group_id == Group.id)
                          .where(GroupMember.student_id == arman.id, Group.capacity == 1))
    assert ind is not None and ind.teacher_id == (await db.scalar(select(User.id).where(User.full_name == "Пробный Ерлан Серикович")))
    rules = list(await db.scalars(select(ScheduleRule).where(ScheduleRule.group_id == ind.id)))
    assert sorted(r_.weekdays for r_ in rules) == [[0, 2, 4], [5]]
    # Attendance: a past mark becomes a held lesson with the mark; the future one is not imported
    marks = list(await db.scalars(select(Attendance).where(Attendance.student_id == a.id)))
    assert [m.status for m in marks] == ["present"] and marks[0].charged is False
    lesson = await db.get(Lesson, marks[0].lesson_id)
    assert lesson.status == "done" and lesson.group_id == g.id
    assert (await db.scalar(select(Attendance).where(Attendance.student_id == arman.id))).status == "absent"
    # Payments: history only — no lessons, not «first», marked imported; tiyn rounded; unpaid invoice skipped
    pays = list(await db.scalars(select(Payment).order_by(Payment.id)))
    assert len(pays) == 4 and {p.source for p in pays} == {"import"} and not any(p.is_first for p in pays)
    assert {p.lessons for p in pays} == {0} and sum(p.amount for p in pays) == 57000 + 4000 + 30000 + 25001
    assert {p.category for p in pays} == {"course", "book"}
    # Nothing was sent, accrued or awarded
    for m in (Notification, OutboundMessage, Accrual, CoinEntry):
        assert await db.scalar(select(func.count()).select_from(m)) == 0, m.__name__
    # Books: catalog + stock in the default branch
    book = await db.scalar(select(Book).where(Book.title == "Elementary"))
    assert book.sale_price == 4000
    assert (await db.scalar(select(BookStock).where(BookStock.book_id == book.id))).qty == 30
    # Communications: into the student's notes; an unknown person becomes a lead in «Отказ»
    assert "перезвонить" in a.notes
    lead = await db.scalar(select(Lead).where(Lead.full_name == "Незнакомый Контакт"))
    assert lead is not None and lead.source == "import"
    # Audited, one entry per file
    from app.models import AuditLog
    assert await db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "import.commit")) == len(fs) + 1

    # Re-import: nothing new, nothing duplicated
    r = await client.post("/api/import/old-crm?commit=true", headers=owner_h, files=upload(fs), data={"default_branch_id": str(y)})
    again = r.json()
    assert again["totals"]["new"] == 0 and again["totals"]["update"] == 0, again["totals"]
    assert await counts(db) == after
    assert (await db.get(Student, a.id)).money_balance == 27000


async def test_reimport_with_changed_balance_applies_the_difference(db, client, owner_h):
    fs = {"students.xlsx": files()["students.xlsx"]}
    y = await branch_id(db, "Янги шахар")
    await client.post("/api/import/old-crm?commit=true", headers=owner_h, files=upload(fs), data={"default_branch_id": str(y)})
    a = await db.scalar(select(Student).where(Student.full_name == "Учебная Алия"))
    assert a.money_balance == 31000  # no payments file in this batch: no books to take out
    changed = files()["students.xlsx"]
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(changed))
    wb.active.cell(row=3, column=29).value = 40000  # «Расход» grew in the old CRM
    buf = io.BytesIO()
    wb.save(buf)
    r = (await client.post("/api/import/old-crm?commit=true", headers=owner_h, files=upload({"students.xlsx": buf.getvalue()}),
                           data={"default_branch_id": str(y)})).json()
    row = next(x for x in r["files"][0]["rows"] if x["label"] == "Учебная Алия")
    assert row["status"] == "update" and "31000 → 21000" in row["reason"]
    assert (await db.get(Student, a.id)).money_balance == 21000
    assert await db.scalar(select(func.count()).select_from(Student).where(Student.full_name == "Учебная Алия")) == 1


async def test_matches_existing_people_and_reports_errors(db, client, owner_h):
    y = await branch_id(db, "Янги шахар")
    s = (await client.post("/api/students", headers=owner_h, json={"full_name": "Учебная Алия", "phone": "+77050000001",
                                                                  "branch_id": y, "create_account": False})).json()
    fs = {"students.xlsx": files()["students.xlsx"]}
    r = (await client.post("/api/import/old-crm", headers=owner_h, files=upload(fs))).json()
    row = next(x for x in r["files"][0]["rows"] if x["label"] == "Учебная Алия")
    assert row["status"] == "update" and "найден" in row["reason"]
    await client.post("/api/import/old-crm?commit=true", headers=owner_h, files=upload(fs))
    assert await db.scalar(select(func.count()).select_from(Student).where(Student.phone == "+77050000001")) == 1
    assert await db.scalar(select(ImportRef.entity_id).where(ImportRef.kind == "student", ImportRef.ext_key == "101")) == s["id"]
    # Payments for a client that was never imported are errors with the reason, the rest still goes in
    pay = {"payments.xlsx": files()["payments.xlsx"]}
    r = (await client.post("/api/import/old-crm", headers=owner_h, files=upload(pay))).json()
    statuses = {x["label"].split(" ·")[0]: (x["status"], x["reason"]) for x in r["files"][0]["rows"]}
    assert statuses["Счёт №7001"][0] == "new" and statuses["Счёт №7004"][0] == "skip"


async def test_bad_files_and_limits(db, client, owner_h):
    r = await client.post("/api/import/old-crm", headers=owner_h, files=[("files", ("x.xlsx", b"not a zip", XLSX))])
    assert r.status_code == 200 and r.json()["files"][0]["error"]
    unknown = csv_bytes([["a", "b"], ["1", "2"]])
    f = (await client.post("/api/import/old-crm", headers=owner_h, files=[("files", ("u.csv", unknown, "text/csv"))])).json()["files"][0]
    assert f["kind"] is None and "тип" in f["error"]
    r = await client.post("/api/import/old-crm", headers=owner_h, files=upload({"t.xlsx": files()["teachers.xlsx"]}),
                          data={"kinds": json.dumps(["nonsense"])})
    assert r.status_code == 400


async def test_only_owner_or_network_admin(db, client, owner_h):
    adm = await make_staff(db, "branch_admin", ["Янги шахар"], "+77020000301", "Админ")
    h = await login(client, adm.phone)
    r = await client.post("/api/import/old-crm", headers=h, files=upload({"t.xlsx": files()["teachers.xlsx"]}))
    assert r.status_code == 403
    assert (await client.get("/api/import/old-crm/kinds", headers=h)).status_code == 403
    kinds = (await client.get("/api/import/old-crm/kinds", headers=owner_h)).json()
    assert [k["code"] for k in kinds][:3] == ["teachers", "groups", "students"]


async def test_imported_staff_gets_a_phone_once(db, client, owner_h):
    await client.post("/api/import/old-crm?commit=true", headers=owner_h, files=upload({"t.xlsx": files()["teachers.xlsx"]}))
    t = await db.scalar(select(User).where(User.full_name == "Тестова Айгуль Маратовна"))
    r = await client.post("/api/auth/login", json={"phone": "+77050000000", "password": "whatever-123"})
    assert r.status_code == 401
    assert (await client.patch(f"/api/staff/{t.id}", headers=owner_h, json={"phone": "+7 705 555 00 11"})).status_code == 200
    assert (await db.get(User, t.id, populate_existing=True)).phone == "+77055550011"
    # A phone already set is never replaced through this field
    assert (await client.patch(f"/api/staff/{t.id}", headers=owner_h, json={"phone": "+77055550012"})).status_code == 400
