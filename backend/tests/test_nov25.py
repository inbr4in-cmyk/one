"""Owner's request of 25.11.2026: lesson plan of a level, picked when marking attendance, test alerts."""
from datetime import time, timedelta

from sqlalchemy import select

from app.models import Lesson, Level, Notification
from app.services import plan
from app.services.clock import at_local, today
from tests.conftest import branch_id, login, make_staff
from tests.test_core_learning import _setup, _student

YANGI = "Янги шахар"


async def test_level_plan_is_picked_at_attendance_shown_ahead_and_warns_before_a_test(client, db, owner_h):
    bid, teacher, room, g = await _setup(db, client, owner_h)
    tid, rid, gid, lvl = teacher.id, room.id, g["id"], g["level_id"]
    (await db.get(Level, lvl)).name = "Elementary"
    await db.flush()
    assert "filled 46 rows" in await plan.seed(db)
    assert "already has 46 rows" in await plan.seed(db)
    rows = (await client.get(f"/api/levels/{lvl}/plan", headers=owner_h)).json()
    assert len(rows) == 46 and rows[14]["kind"] == "progress_test" and rows[14]["month"] == 2 and rows[14]["num"] == 3
    assert rows[45]["kind"] == "final_test" and rows[0]["title"].startswith("1A Grammar Bank")
    # the plan is edited in «Справочники»: a row renamed, one removed, one added
    body = {"rows": [{**rows[0], "title": "1A Grammar Bank (new)"}, *rows[2:], {"month": 4, "title": "Extra", "kind": "lesson"}]}
    r = await client.put(f"/api/levels/{lvl}/plan", headers=owner_h, json=body)
    assert r.status_code == 200 and len(r.json()) == 46 and r.json()[0]["title"].endswith("(new)") and r.json()[0]["id"] == rows[0]["id"]
    rows = r.json()
    meth = await make_staff(db, "branch_admin", [YANGI], "+77052227401", "Методист План")
    from app.models import Role, UserRole
    role = Role(code="methodist_t", name="Методист")
    db.add(role)
    await db.flush()
    db.add(UserRole(user_id=meth.id, role_id=role.id))
    meth_id = meth.id
    sid = (await _student(db, client, owner_h, bid, "План Урок", "+77052227402"))["id"]
    await client.post(f"/api/groups/{gid}/members", headers=owner_h, json={"student_id": sid, "joined_on": (today() - timedelta(days=9)).isoformat()})
    ids = []
    for back in (3, 2, 1, -1, -2):
        d = today() - timedelta(days=back)
        x = Lesson(branch_id=bid, group_id=gid, level_id=lvl, teacher_id=tid, room_id=rid,
                   starts_at=at_local(d, time(15, 0)), ends_at=at_local(d, time(16, 0)))
        db.add(x)
        await db.flush()
        ids.append(x.id)
    await db.commit()

    async def week():
        r = await client.get(f"/api/lessons?from={today() - timedelta(days=3)}&to={today() + timedelta(days=2)}", headers=owner_h)
        return {x["id"]: x for x in r.json()}

    w = await week()  # a group that has not held a lesson starts from the first row
    assert [w[i]["plan_no"] for i in ids] == [1, 2, 3, 4, 5] and all(w[i]["plan_guess"] for i in ids)
    marks = {"marks": [{"student_id": sid, "status": "present"}], "reason": "позже"}
    r = await client.put(f"/api/lessons/{ids[0]}/attendance", headers=owner_h, json=marks)
    assert r.status_code == 400 and "по плану" in r.text  # the plan lesson is required
    assert (await client.put(f"/api/lessons/{ids[0]}/attendance", headers=owner_h, json={**marks, "plan_item_id": 999999})).status_code == 400
    ro = (await client.get(f"/api/lessons/{ids[0]}/attendance", headers=owner_h)).json()
    assert len(ro["plan"]) == 46 and ro["lesson"]["plan_item_id"] == rows[0]["id"] and ro["lesson"]["plan_guess"] is True
    # the group is already at lesson 13: the teacher picks it, the coming lessons follow from there
    r = await client.put(f"/api/lessons/{ids[0]}/attendance", headers=owner_h, json={**marks, "plan_item_id": rows[11]["id"]})
    assert r.status_code == 200 and r.json()["lesson"]["plan_no"] == 12 and r.json()["lesson"]["plan_guess"] is False
    assert not list(await db.scalars(select(Notification).where(Notification.user_id == meth_id, Notification.title.like("%Progress Test%"))))
    w = await week()
    assert [w[i]["plan_no"] for i in ids] == [12, 13, 14, 15, 16] and w[ids[3]]["plan_kind"] == "progress_test"
    # a correction without picking again keeps the row; the lesson before the test tells the methodist
    assert (await client.put(f"/api/lessons/{ids[0]}/attendance", headers=owner_h, json=marks)).status_code == 200
    assert (await client.put(f"/api/lessons/{ids[1]}/attendance", headers=owner_h, json={**marks, "plan_item_id": rows[12]["id"]})).status_code == 200
    for _ in range(2):  # re-saving does not repeat the alert
        r = await client.put(f"/api/lessons/{ids[2]}/attendance", headers=owner_h, json={**marks, "plan_item_id": rows[13]["id"]})
        assert r.status_code == 200, r.text
    notes = list(await db.scalars(select(Notification).where(Notification.user_id == meth_id, Notification.title.like("%Progress Test%"))))
    assert len(notes) == 1 and "Progress Test 1 Day 1" in notes[0].title and "Дана Учитель" in notes[0].body


async def test_group_test_is_planned_taken_online_annulled_restored_and_ranked(client, db, owner_h):
    from app.core.security import hash_password
    from app.models import Attempt, GroupMember, Question, Student, Test, User
    from app.models.identity import UserKind
    from tests.conftest import PASSWORD, login

    bid, teacher, room, g = await _setup(db, client, owner_h)
    tid, rid, gid, lvl = teacher.id, room.id, g["id"], g["level_id"]
    r = await client.post("/api/tests", headers=owner_h, json={"kind": "progress", "title": "Progress Test 1", "level_id": lvl, "max_score": 3})
    assert r.status_code == 201, r.text
    test_id = r.json()["id"]
    for i in range(3):
        r = await client.post(f"/api/tests/{test_id}/questions", headers=owner_h, json={
            "order": i, "kind": "single", "text": f"Q{i}", "options": ["a", "b", "c"], "correct": [1], "points": 1})
        assert r.status_code == 201, r.text
    hs, sids = [], []
    for i, phone in enumerate(("+77052227411", "+77052227412")):
        s = await _student(db, client, owner_h, bid, f"Тест Ученик {i}", phone)
        u = User(kind=UserKind.STUDENT, phone=f"+7705222742{i}", full_name=s["full_name"], password_hash=hash_password(PASSWORD))
        db.add(u)
        await db.flush()
        (await db.get(Student, s["id"])).user_id = u.id
        await client.post(f"/api/groups/{gid}/members", headers=owner_h, json={"student_id": s["id"], "joined_on": (today() - timedelta(days=5)).isoformat()})
        sids.append(s["id"])
        await db.commit()
        hs.append(await login(client, u.phone))
    lesson = Lesson(branch_id=bid, group_id=gid, level_id=lvl, teacher_id=tid, room_id=rid,
                    starts_at=at_local(today(), time(15, 0)), ends_at=at_local(today(), time(16, 0)))
    db.add(lesson)
    await db.flush()
    lid = lesson.id
    await db.commit()
    r = await client.post("/api/test-sessions", headers=owner_h, json={"group_id": gid, "test_id": test_id, "lesson_id": lid})
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    assert (await client.post("/api/test-sessions", headers=owner_h, json={"group_id": gid, "test_id": test_id, "lesson_id": lid})).status_code == 409
    w = (await client.get(f"/api/lessons?from={today()}&to={today()}", headers=owner_h)).json()
    assert next(x for x in w if x["id"] == lid)["test_title"] == "Progress Test 1"
    # not started yet: the student sees it but cannot begin
    mine = (await client.get(f"/api/portal/tests?student_id={sids[0]}", headers=hs[0])).json()
    assert [x["status"] for x in mine] == ["planned"]
    assert (await client.post(f"/api/portal/tests/{sid}/begin", headers=hs[0], json={"student_id": sids[0]})).status_code == 409
    r = await client.post(f"/api/test-sessions/{sid}/start", headers=owner_h, json={"time_limit_min": 40})
    assert r.status_code == 200 and r.json()["status"] == "running" and r.json()["time_limit_min"] == 40
    # another student's test is not reachable
    assert (await client.post(f"/api/portal/tests/{sid}/begin", headers=hs[0], json={"student_id": sids[1]})).status_code == 404

    async def take(i, picks, leave_after=None):
        st = (await client.post(f"/api/portal/tests/{sid}/begin", headers=hs[i], json={"student_id": sids[i]})).json()
        assert st["attempt"]["total"] == 3 and "correct" not in st["question"]
        n = 0
        while st["question"]:
            q = st["question"]
            if leave_after is not None and n == leave_after:
                return st
            r = await client.post(f"/api/portal/tests/{sid}/answer", headers=hs[i], json={"student_id": sids[i], "question_id": q["id"], "answer": [picks[n]]})
            assert r.status_code == 200, r.text
            # the answered question cannot be answered again
            assert (await client.post(f"/api/portal/tests/{sid}/answer", headers=hs[i], json={"student_id": sids[i], "question_id": q["id"], "answer": [1]})).status_code in (200, 409)
            st, n = r.json(), n + 1
        return st

    st = await take(0, [1, 1, 0])
    assert st["attempt"]["status"] == "done" and st["attempt"]["score"] == 2 and st["attempt"]["duration_sec"] is not None
    st = await take(1, [1, 1, 1], leave_after=1)
    r = await client.post(f"/api/portal/tests/{sid}/leave", headers=hs[1], json={"student_id": sids[1]})
    assert r.json()["attempt"]["status"] == "void" and r.json()["question"] is None
    q_id = st["question"]["id"]
    r = await client.post(f"/api/portal/tests/{sid}/answer", headers=hs[1], json={"student_id": sids[1], "question_id": q_id, "answer": [1]})
    assert r.json()["attempt"]["status"] == "void" and r.json()["attempt"]["position"] == 1  # annulled: nothing is accepted
    board = (await client.get(f"/api/test-sessions/{sid}", headers=owner_h)).json()
    assert {x["student_id"]: x["status"] for x in board["rows"]} == {sids[0]: "done", sids[1]: "void"}
    r = await client.post(f"/api/test-sessions/{sid}/restore", headers=owner_h, json={"student_id": sids[1]})
    assert r.status_code == 200
    st = (await client.get(f"/api/portal/tests/{sid}?student_id={sids[1]}", headers=hs[1])).json()
    assert st["attempt"]["status"] == "in_progress" and st["attempt"]["position"] == 1 and st["question"]["id"] == q_id
    for _ in range(2):
        st = (await client.post(f"/api/portal/tests/{sid}/answer", headers=hs[1], json={"student_id": sids[1], "question_id": st["question"]["id"], "answer": [1]})).json()
    assert st["attempt"]["status"] == "done" and st["attempt"]["score"] == 3
    board = (await client.post(f"/api/test-sessions/{sid}/finish", headers=owner_h)).json()
    assert board["status"] == "finished"
    assert {x["student_id"]: x["place"] for x in board["rows"]} == {sids[1]: 1, sids[0]: 2}
    hist = (await client.get(f"/api/students/{sids[1]}/tests", headers=owner_h)).json()
    assert hist[0]["score"] == 3 and hist[0]["duration_sec"] is not None and hist[0]["test_title"] == "Progress Test 1"
    orders = [a.q_order for a in await db.scalars(select(Attempt).where(Attempt.session_id == sid))]
    assert all(sorted(o) == sorted(orders[0]) for o in orders)


async def test_form_is_filled_by_link_kept_like_an_application_and_seen_by_admins_only(client, db, owner_h):
    from app.models import FormResponse

    forms = (await client.get("/api/forms", headers=owner_h)).json()
    assert len(forms) == 1 and forms[0]["questions"] == 31 and forms[0]["sections"] == 4 and forms[0]["is_open"]
    fid, token = forms[0]["id"], forms[0]["path"].split("/")[-1]
    north = await branch_id(db, "Север")
    teacher = await make_staff(db, "teacher", ["Север"], "+77075550001", "Учитель Анкеты")
    th = await login(client, "+77075550001")
    pub = (await client.get(f"/api/public/forms/{token}")).json()
    assert teacher.id in [t["id"] for t in pub["teachers"]] and len(pub["sections"]) == 4
    base = {"q1": "Айдана Серикова", "q2": "8 701 555 00 11", "q3": north, "q4": teacher.id, "q6": 0}
    trial = {"q7": 9, "q8": 6, "q9": 10, "q10": 0, "q11": 1, "q12": 10, "q15": 1, "q16": {"picked": [1], "other": "далеко"}}
    last = {"q30": 9, "q31": 1}
    # a required question of the person's own path is missing
    r = await client.post(f"/api/public/forms/{token}", json={"answers": {**base, **last}})
    assert r.status_code == 400
    # answers of the other branch of the form (new student) are dropped
    r = await client.post(f"/api/public/forms/{token}", json={"answers": {**base, **trial, **last, "q18": 2}})
    assert r.status_code == 201, r.text
    row = await db.scalar(select(FormResponse))
    assert row.phone == "+77015550011" and row.branch_id == north and row.teacher_id == teacher.id and "q18" not in row.answers
    assert row.flags == ["Оценка 6: Насколько понятно преподаватель объяснял материал?", "Нужно подумать"]
    # teachers never see the answers
    assert (await client.get(f"/api/forms/{fid}/responses", headers=th)).status_code == 403
    rows = (await client.get(f"/api/forms/{fid}/responses?status=new", headers=owner_h)).json()
    assert len(rows) == 1 and rows[0]["kind"] == "Пробный урок" and rows[0]["branch"] == "Север"
    full = (await client.get(f"/api/form-responses/{rows[0]['id']}", headers=owner_h)).json()
    assert [s["title"] for s in full["sections"]] == ["Общие вопросы", "Пробный урок", "Последние вопросы"]
    assert {"text": "Что может помешать начать обучение?", "value": "Цена, Другое: далеко", "low": False} in full["sections"][1]["items"]
    r = await client.post(f"/api/form-responses/{rows[0]['id']}/done", headers=owner_h, json={"note": "Позвонили"})
    assert r.json()["status"] == "done"
    sm = (await client.get(f"/api/forms/{fid}/summary", headers=owner_h)).json()
    q16 = next(q for q in sm["questions"] if q["id"] == "q16")
    assert q16["options"][1]["by_branch"] == {str(north): 1} and q16["options"][-1]["total"] == 1
    # closed: the link asks to sign in, a signed-in person can still send
    assert (await client.patch(f"/api/forms/{fid}", headers=owner_h, json={"is_open": False})).json()["is_open"] is False
    assert (await client.get(f"/api/public/forms/{token}")).json() == {"title": forms[0]["title"], "closed": True}
    assert (await client.post(f"/api/public/forms/{token}", json={"answers": {**base, **trial, **last}})).status_code == 403
    assert (await client.post(f"/api/my/forms/{token}", headers=th, json={"answers": {**base, **trial, **last}})).status_code == 201


async def test_daily_report_counts_the_day_and_names_the_people(client, db, owner_h):
    r = await client.post("/api/crm/leads", headers=owner_h, json={"full_name": "Лид Дня", "phone": "+77075550101", "source": "walk_in",
                                                               "branch_id": await branch_id(db, "Север")})
    assert r.status_code in (200, 201), r.text
    lid = r.json()["id"]
    r = await client.post(f"/api/crm/leads/{lid}/events", headers=owner_h, json={"kind": "call", "text": "Позвонили", "result": "thinking"})
    assert r.status_code in (200, 201), r.text
    rep = (await client.get("/api/dashboard/day", headers=owner_h)).json()
    assert rep["leads"]["new"]["count"] == 1 and rep["leads"]["new"]["items"][0]["full_name"] == "Лид Дня"
    assert rep["leads"]["contacted"]["count"] == 1 and rep["leads"]["trial"]["count"] == 0 and rep["leads"]["paid"]["count"] == 0
    assert "debtors" in rep and rep["payers"] == {"count": 0, "total": 0, "items": []}
    y = (today() - timedelta(days=1)).isoformat()
    assert (await client.get(f"/api/dashboard/day?day={y}", headers=owner_h)).json()["leads"]["new"]["count"] == 0
