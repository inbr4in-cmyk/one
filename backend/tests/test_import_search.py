import io

from openpyxl import Workbook
from sqlalchemy import select

from app.models import GroupMember, Student
from tests.conftest import branch_id, level_id, login, make_staff


def _xlsx(rows):
    wb = Workbook()
    ws = wb.active
    ws.append(["ФИО", "Телефон", "Дата рождения", "Филиал", "Уровень", "Группа", "Осталось уроков", "Цена урока",
               "ФИО родителя", "Телефон родителя"])
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


async def test_import_preview_then_commit(db, client, owner_h):
    y = await branch_id(db, "Янги шахар")
    t = await make_staff(db, "teacher", ["Янги шахар"], "+77020000070")
    await client.post("/api/groups", headers=owner_h, json={"name": "EL-9", "branch_id": y, "level_id": await level_id(db, "ELE"),
                                                            "teacher_id": t.id, "capacity": 10})
    good = [["Мадина Ахметова", "8 705 111 44 55", "05.06.2013", "Янги шахар", "ELE", "EL-9", 5, 3000, "Гульнара", "87051114499"],
            ["Арман Сеитов", "", "", "Янги шахар", "BEG", "", 0, "", "", ""]]
    bad = good + [["Без филиала", "+77050000000", "", "Неизвестный", "", "", 0, 0, "", ""],
                  ["Дубль", "87051114455", "", "Янги шахар", "", "", 0, 0, "", ""]]
    files = {"file": ("s.xlsx", _xlsx(bad), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    r = (await client.post("/api/import/students", headers=owner_h, files=files)).json()
    assert r["valid"] == 2 and {e["row"] for e in r["errors"]} == {4, 5}
    assert (await client.post("/api/import/students?commit=true", headers=owner_h, files=files)).status_code == 400
    files = {"file": ("s.xlsx", _xlsx(good), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    assert (await client.post("/api/import/students?commit=true", headers=owner_h, files=files)).json()["created"] == 2
    s = await db.scalar(select(Student).where(Student.phone == "+77051114455"))
    assert s.lessons_left == 5 and s.balance_lesson_price == 3000 and s.user_id
    assert await db.scalar(select(GroupMember).where(GroupMember.student_id == s.id))
    found = (await client.get("/api/search?q=Мадина", headers=owner_h)).json()
    assert found["students"][0]["id"] == s.id
    # A teacher of another branch finds nothing
    t2 = await make_staff(db, "teacher", ["Север"], "+77020000071")
    th = await login(client, t2.phone)
    assert (await client.get("/api/search?q=Мадина", headers=th)).json()["students"] == []
