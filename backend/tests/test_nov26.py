"""WhatsApp linked by QR (owner, 25.11.2026): only incoming chats and managers' manual answers go through the link."""
import json
from datetime import timedelta

from sqlalchemy import select

from app.core.config import get_settings
from app.models import Conversation, ExternalMessage
from app.services import meta, wa_bridge
from app.services.clock import now
from tests.conftest import login, make_staff

SECRET = "b" * 40
URL = "/api/webhooks/wa-bridge"
JH = {"Content-Type": "application/json"}


def _on(monkeypatch, state="open", lines=(0,)):
    monkeypatch.setattr(get_settings(), "wa_bridge_url", "http://127.0.0.1:8720")
    monkeypatch.setattr(get_settings(), "wa_bridge_secret", SECRET)
    calls = []

    async def fake(method, path, json=None, timeout=20):
        calls.append((method, path, json))
        if path == "/send":
            return {"id": f"OUT{len(calls)}"}
        if path == "/logout":
            return {"state": "off"}
        one = {"state": state if path == "/status" else "qr", "qr": "2@qr-data", "me": {"phone": "77000000000", "name": "One"},
               "linked_at": 1795000000, "pending": 0, "last_close": None}
        return {"lines": {str(n): one for n in lines}} if path == "/status" else one
    monkeypatch.setattr(wa_bridge, "_call", fake)
    wa_bridge.forget()
    return calls


def _ev(type_, mid, chat, text, **kw):
    return {"type": type_, "id": mid, "chat": chat, "phone": chat if chat.isdigit() else None, "name": "Айгерим", "kind": "text",
            "text": text, "ts": int(now().timestamp()), **kw}


async def _post(client, events, **headers):
    return await client.post(URL, content=json.dumps({"events": events}), headers={**JH, **headers})


async def test_link_webhook_takes_messages_only_with_the_secret_and_only_locally(client, db, owner_h, monkeypatch):
    ev = [_ev("in", "A1", "77011117070", "Здравствуйте")]
    assert (await _post(client, ev, **{"X-Bridge-Secret": SECRET})).status_code == 401  # the link is not set up
    _on(monkeypatch)
    assert (await _post(client, ev)).status_code == 401
    assert (await _post(client, ev, **{"X-Bridge-Secret": "x" * 40})).status_code == 401
    assert (await _post(client, ev, **{"X-Bridge-Secret": SECRET, "X-Real-IP": "8.8.8.8"})).status_code == 404  # came through nginx
    for _ in range(2):  # the service repeats a batch after a failure: stored once
        r = await _post(client, ev + [{"type": "in", "id": "bad", "chat": "../x", "text": "?"}, "junk"], **{"X-Bridge-Secret": SECRET})
        assert r.status_code == 200
    conv = (await client.get("/api/inbox/conversations", headers=owner_h)).json()
    assert len(conv) == 1 and conv[0]["channel"] == "whatsapp" and conv[0]["lead"]["full_name"] == "Айгерим"
    assert conv[0]["unread"] == 1 and conv[0]["contact"]["phone"] == "+77011117070"


async def test_manager_answers_through_the_link_without_the_24h_window(client, db, owner_h, monkeypatch):
    calls = _on(monkeypatch)
    h = {"X-Bridge-Secret": SECRET}
    await _post(client, [_ev("in", "B1", "77011117071", "Сколько стоит?"), _ev("in", "B2", "lid:123456789", None, kind="image")], **h)
    convs = {c["contact"]["phone"]: c for c in (await client.get("/api/inbox/conversations", headers=owner_h)).json()}
    assert len(convs) == 2 and convs[None]["last_preview"] == "Фото"  # WhatsApp hid the number: the chat still works
    cid = convs["+77011117071"]["id"]
    conv = await db.get(Conversation, cid)
    conv.last_inbound_at = now() - timedelta(days=3)
    await db.commit()
    assert (await client.get(f"/api/inbox/conversations/{cid}", headers=owner_h)).json()["in_window"] is True

    async def no_meta(*a, **k):
        raise AssertionError("an answer must not go through Meta while the link is on")
    monkeypatch.setattr(meta, "_post", no_meta)
    r = await client.post(f"/api/inbox/conversations/{cid}/messages", headers=owner_h, json={"text": "Добрый день!"})
    assert r.status_code == 201 and r.json()["status"] == "sent", r.text
    assert calls[-1] == ("POST", "/send", {"line": 0, "to": "77011117071", "text": "Добрый день!"})
    r = await client.post(f"/api/inbox/conversations/{convs[None]['id']}/messages", headers=owner_h, json={"text": "Здравствуйте"})
    assert r.status_code == 201 and calls[-1][2]["to"] == "lid:123456789", r.text

    # typed on the phone: shown in a chat the site has, never opens a chat with somebody the school does not know
    r = await _post(client, [_ev("out", "B3", "77011117071", "Ответ с телефона"), _ev("out", "B4", "77770001122", "Личное")], **h)
    assert r.json()["stored"] == 1
    texts = list(await db.scalars(select(ExternalMessage.text).where(ExternalMessage.conversation_id == cid).order_by(ExternalMessage.id)))
    assert texts == ["Сколько стоит?", "Добрый день!", "Ответ с телефона"]
    assert await db.scalar(select(ExternalMessage.id).where(ExternalMessage.text == "Личное")) is None

    # the link dropped: the usual 24 h rule is back and nothing is sent
    _on(monkeypatch, state="connecting")
    r = await client.post(f"/api/inbox/conversations/{cid}/messages", headers=owner_h, json={"text": "Ещё"})
    assert r.status_code == 409


async def test_notifications_and_login_codes_never_use_the_link(client, db, owner_h, monkeypatch):
    calls = _on(monkeypatch)
    assert meta.wa_configured() is False
    res = await meta.wa_send_text("+77011117072", "Напоминание об уроке")
    assert res.ok is False or not any(c[1] == "/send" for c in calls)
    assert not any(c[1] == "/send" for c in calls)


async def test_only_the_owner_links_and_unlinks(client, db, owner_h, monkeypatch):
    r = await client.get("/api/settings/whatsapp-link", headers=owner_h)
    assert r.json() and all(x["state"] == "disabled" and x["qr"] is None for x in r.json())
    assert (await client.post("/api/settings/whatsapp-link/connect", headers=owner_h)).status_code == 409
    calls = _on(monkeypatch, state="qr")
    r = await client.post("/api/settings/whatsapp-link/connect", headers=owner_h)
    assert r.status_code == 200 and r.json()["qr"] == "2@qr-data" and r.json()["can_manage"] is True
    await make_staff(db, "branch_admin", ["Север"], "+77052228801", "Админ Филиала")
    await db.commit()
    bh = await login(client, "+77052228801")
    r = await client.get("/api/settings/whatsapp-link", headers=bh)
    assert r.status_code in (200, 403) and (r.status_code == 403 or all(x["qr"] is None for x in r.json()))
    assert (await client.post("/api/settings/whatsapp-link/connect", headers=bh)).status_code == 403
    assert (await client.post("/api/settings/whatsapp-link/disconnect", headers=bh)).status_code == 403
    r = await client.post("/api/settings/whatsapp-link/disconnect", headers=owner_h)
    assert r.status_code == 200 and r.json()["state"] == "off" and ("POST", "/logout", {"line": 0}) in calls


async def test_each_branch_has_its_own_whatsapp_number(client, db, owner_h, monkeypatch):
    """Owner, 27.11.2026: a number per branch. The lead gets the branch of the number, the answer leaves from it."""
    from app.models import Lead
    from tests.conftest import branch_id

    north, south = await branch_id(db, "Север"), await branch_id(db, "Янги шахар")
    calls = _on(monkeypatch, lines=(north, south))
    h = {"X-Bridge-Secret": SECRET}
    r = await _post(client, [_ev("in", "L1", "77011118001", "Запишите на пробный", line=north),
                             _ev("in", "L2", "77011118002", "Здравствуйте", line=south),
                             _ev("in", "L3", "77011118001", "И к вам тоже", line=south),  # the same person, the other branch
                             _ev("in", "L4", "77011118003", "?", line=999999)], **h)  # a number of no branch
    assert r.json()["stored"] == 4
    convs = (await client.get("/api/inbox/conversations", headers=owner_h)).json()
    by = {(c["contact"]["phone"], c["wa_line"]): c for c in convs}
    assert set(by) == {("+77011118001", north), ("+77011118002", south), ("+77011118001", south), ("+77011118003", 999999)}
    assert by[("+77011118001", north)]["branch_id"] == north and by[("+77011118002", south)]["branch_id"] == south
    assert by[("+77011118001", south)]["branch_id"] == south and by[("+77011118003", 999999)]["branch_id"] is None
    lead = await db.get(Lead, by[("+77011118001", north)]["lead"]["id"])
    assert lead.branch_id == north and by[("+77011118001", south)]["lead"]["id"] == lead.id  # one card for one person

    r = await client.post(f"/api/inbox/conversations/{by[('+77011118002', south)]['id']}/messages", headers=owner_h, json={"text": "Добрый день"})
    assert r.status_code == 201 and calls[-1] == ("POST", "/send", {"line": south, "to": "77011118002", "text": "Добрый день"})
    # typed on the phone of the northern branch: lands in that branch's chat only
    await _post(client, [_ev("out", "L5", "77011118001", "С телефона Севера", line=north)], **h)
    texts = list(await db.scalars(select(ExternalMessage.text).where(
        ExternalMessage.conversation_id == by[("+77011118001", north)]["id"]).order_by(ExternalMessage.id)))
    assert texts == ["Запишите на пробный", "С телефона Севера"]

    # only one branch is linked now: the other one's chat falls back to the 24 h rule of the official number
    _on(monkeypatch, lines=(south,))
    assert (await client.get(f"/api/inbox/conversations/{by[('+77011118001', north)]['id']}", headers=owner_h)).json()["free_reply"] is False
    cards = (await client.get("/api/settings/whatsapp-link", headers=owner_h)).json()
    assert {(x["line"], x["state"]) for x in cards} >= {(north, "off"), (south, "open")} and all(x["line"] for x in cards)
    assert (await client.post("/api/settings/whatsapp-link/connect", headers=owner_h, json={"line": 424242})).status_code == 404
    r = await client.post("/api/settings/whatsapp-link/connect", headers=owner_h, json={"line": north})
    assert r.status_code == 200 and r.json()["line"] == north and r.json()["branch"] == "Север"


async def test_official_numbers_of_the_branches(client, db, owner_h, monkeypatch):
    """Meta: several numbers of one WhatsApp account. The webhook says which number got the message."""
    from tests.conftest import branch_id

    north = await branch_id(db, "Север")
    assert (await client.put("/api/settings/wa_numbers", headers=owner_h, json={"value": {str(north): "111222333"}})).status_code == 204
    monkeypatch.setattr(get_settings(), "wa_phone_number_id", "999000")
    monkeypatch.setattr(get_settings(), "wa_access_token", "t" * 30)
    sent = []

    async def fake_post(url, token, payload):
        sent.append(url)
        return meta.SendResult(True, external_id=f"wamid.{len(sent)}")
    monkeypatch.setattr(meta, "_post", fake_post)

    def hook(phone_id, mid, frm):
        return {"object": "whatsapp_business_account", "entry": [{"changes": [{"field": "messages", "value": {
            "metadata": {"phone_number_id": phone_id}, "contacts": [{"wa_id": frm, "profile": {"name": "Клиент"}}],
            "messages": [{"from": frm, "id": mid, "timestamp": str(int(now().timestamp())), "type": "text", "text": {"body": "Привет"}}]}}]}]}
    from app.modules.inbox.service import handle_meta_payload

    assert await handle_meta_payload(db, hook("111222333", "wamid.A", "77011119001")) == 1
    assert await handle_meta_payload(db, hook("999000", "wamid.B", "77011119002")) == 1
    await db.commit()
    by = {c["contact"]["phone"]: c for c in (await client.get("/api/inbox/conversations", headers=owner_h)).json()}
    assert by["+77011119001"]["wa_line"] == north and by["+77011119001"]["branch_id"] == north
    assert by["+77011119002"]["wa_line"] is None and by["+77011119002"]["branch_id"] is None
    for phone in ("+77011119001", "+77011119002"):
        assert (await client.post(f"/api/inbox/conversations/{by[phone]['id']}/messages", headers=owner_h, json={"text": "Ответ"})).status_code == 201
    assert sent[0].endswith("/111222333/messages") and sent[1].endswith("/999000/messages")
    # login codes and notifications go from the first number
    await meta.wa_send_text("+77011119003", "Код")
    assert sent[-1].endswith("/999000/messages")


async def test_dashboard_day_counts_left_paused_and_sources_of_the_period(client, db, owner_h):
    """Owner, 26.11.2026: «ушли / на паузе» and lead sources follow the chosen day or month."""
    from datetime import date as _d

    from app.models import Freeze, Lead, Student
    from app.models.learning import StudentStatus
    from app.services.clock import today
    from tests.conftest import branch_id
    from tests.test_core_learning import _student

    bid = await branch_id(db, "Янги шахар")
    a = await _student(db, client, owner_h, bid, "Ушёл Сегодня", "+77052229901")
    b = await _student(db, client, owner_h, bid, "Ушёл Давно", "+77052229902")
    c = await _student(db, client, owner_h, bid, "На Паузе", "+77052229903")
    owner_id = (await client.get("/api/auth/me", headers=owner_h)).json()["id"]
    for sid, back in ((a["id"], 0), (b["id"], 70)):
        s = await db.get(Student, sid)
        s.status, s.left_at = StudentStatus.LEFT, now() - timedelta(days=back)
    db.add(Freeze(student_id=c["id"], starts_on=today() - timedelta(days=2), ends_on=today() + timedelta(days=5), created_by=owner_id))
    await db.commit()
    before = (await client.get(f"/api/dashboard/day?day={today()}", headers=owner_h)).json()
    r = await client.post("/api/crm/leads", headers=owner_h, json={"full_name": "Лид Источник", "phone": "+77052229904", "branch_id": bid, "source": "instagram"})
    assert r.status_code in (200, 201), r.text
    rep = (await client.get(f"/api/dashboard/day?day={today()}", headers=owner_h)).json()
    assert rep["gone"]["left"] == 1 and rep["gone"]["frozen"] == 1
    assert rep["sources"].get("instagram", 0) == before["sources"].get("instagram", 0) + 1
    y = today() - timedelta(days=10)
    old = (await client.get(f"/api/dashboard/day?day={y}", headers=owner_h)).json()
    assert old["gone"]["left"] == 0 and old["gone"]["frozen"] == 0 and old["sources"] == {}
    rows = (await client.get(f"/api/dashboard/students?status=left&day={today()}", headers=owner_h)).json()
    assert [x["full_name"] for x in rows] == ["Ушёл Сегодня"]
    assert len((await client.get("/api/dashboard/students?status=left", headers=owner_h)).json()) == 2
    rows = (await client.get(f"/api/dashboard/students?status=frozen&month={today():%Y-%m}", headers=owner_h)).json()
    assert [x["full_name"] for x in rows] == ["На Паузе"] and _d.fromisoformat(rows[0]["until"]) == today() + timedelta(days=5)


async def test_form_with_many_low_scores_is_saved(client, db, owner_h):
    """Owner, 26.11.2026: the form answered «Некорректные данные…» — the call-today notice was longer than its column."""
    from app.models import Form

    assert (await client.get("/api/forms", headers=owner_h)).status_code == 200  # creates the school's form
    f = await db.scalar(select(Form))
    await make_staff(db, "teacher", ["Янги шахар", "Север"], "+77052230001", "Учитель Анкеты")
    await db.commit()
    pub = (await client.get(f"/api/public/forms/{f.token}")).json()
    answers = {}
    for _ in range(4):  # the route depends on the answers: fill what is asked, lowest marks everywhere
        r = await client.post(f"/api/public/forms/{f.token}", json={"answers": answers})
        if r.status_code == 201:
            break
        for s in f.sections:
            for q in s["questions"]:
                k = q["kind"]
                answers.setdefault(q["id"], "Очень Длинное Имя " * 9 if k == "short" else "+77051230099" if k == "phone" else "текст" if k == "para"
                                   else q["min"] if k == "scale" else {"picked": [0]} if k == "multi"
                                   else pub["branches"][0]["id"] if k == "branch" else (pub["teachers"] or [{"id": None}])[0]["id"] if k == "teacher"
                                   else next((i for i, o in enumerate(q["options"]) if o.get("alert")), 0))
    assert r.status_code == 201, r.text
    row = (await client.get(f"/api/forms/{f.id}/responses", headers=owner_h)).json()
    assert len(row["items"] if isinstance(row, dict) else row) == 1


async def test_students_export_is_for_administrators_only(client, db, owner_h):
    """Owner, 27.11.2026: «Экспорт» in the students list, administrators only; a branch administrator gets his branch."""
    import io

    from openpyxl import load_workbook

    from tests.conftest import branch_id
    from tests.test_core_learning import _student

    north, south = await branch_id(db, "Север"), await branch_id(db, "Янги шахар")
    await _student(db, client, owner_h, north, "Экспорт Северный", "+77052227701")
    await _student(db, client, owner_h, south, "=Экспорт Южный", "+77052227702")
    r = await client.get("/api/students/export.xlsx", headers=owner_h)
    assert r.status_code == 200 and "spreadsheetml" in r.headers["content-type"], r.text
    ws = load_workbook(io.BytesIO(r.content)).active
    names = [row[0].value for row in ws.iter_rows(min_row=2)]
    assert "Экспорт Северный" in names and "=Экспорт Южный" in names
    assert all(c.data_type == "s" for row in ws.iter_rows(min_row=2) for c in row[:1])  # a name is never a formula
    await make_staff(db, "branch_admin", ["Север"], "+77052227703", "Админ Севера")
    await make_staff(db, "teacher", ["Север"], "+77052227704", "Учитель Севера")
    await make_staff(db, "sales", ["Север"], "+77052227705", "Менеджер Севера")
    await db.commit()
    r = await client.get("/api/students/export.xlsx", headers=await login(client, "+77052227703"))
    names = [row[0].value for row in load_workbook(io.BytesIO(r.content)).active.iter_rows(min_row=2)]
    assert r.status_code == 200 and "Экспорт Северный" in names and "=Экспорт Южный" not in names
    for phone in ("+77052227704", "+77052227705"):
        assert (await client.get("/api/students/export.xlsx", headers=await login(client, phone))).status_code == 403
    assert (await client.get("/api/students/export.xlsx")).status_code == 401


async def test_tasks_newest_first_and_complaint_pops_up_for_admins(client, db, owner_h, monkeypatch):
    """Owner, 27.11.2026: tasks by date, the newest on top; a new complaint pops up on the administrators' screens."""
    owner_id = (await client.get("/api/auth/me", headers=owner_h)).json()["id"]
    for title, due in (("Первая", "2026-12-20T10:00:00+05:00"), ("Вторая", None), ("Третья", "2026-12-01T10:00:00+05:00")):
        r = await client.post("/api/tasks", headers=owner_h, json={"title": title, "assignee_ids": [owner_id], "due_at": due})
        assert r.status_code in (200, 201), r.text
    rows = (await client.get("/api/tasks?box=mine", headers=owner_h)).json()["items"]
    assert [x["title"] for x in rows][:3] == ["Третья", "Вторая", "Первая"]
    rows = (await client.get("/api/tasks?box=mine&sort=due", headers=owner_h)).json()["items"]
    assert [x["title"] for x in rows][:3] == ["Третья", "Первая", "Вторая"]

    from app.services import crm
    popped = []

    async def fake_publish(channel, payload):
        popped.append((channel, payload))
    import app.services.realtime as rt
    monkeypatch.setattr(rt, "publish", fake_publish)
    await make_staff(db, "teacher", ["Север"], "+77052226601", "Учитель Жалоба")
    await db.commit()
    th = await login(client, "+77052226601")
    r = await client.post("/api/complaints", headers=th, json={"subject": "Холодно в кабинете", "body": "В кабинете 3 не работает отопление"})
    assert r.status_code in (200, 201), r.text
    assert any(ch == f"user:{owner_id}" and p.get("kind") == "complaint" for ch, p in popped)
    assert (await client.get("/api/complaints", headers=th)).status_code == 403  # the list is for administrators only
    assert crm.alert


async def test_missed_individual_lesson_pays_half_of_its_own_rate_and_old_ones_are_counted_again(client, db, owner_h):
    from app.models import Accrual, Level, Room
    from app.services import plan
    from app.services.payroll import recalc_noshow
    from tests.conftest import branch_id, level_id
    from tests.test_core_learning import _lesson_now, _student

    bid = await branch_id(db, "Янги шахар")
    teachers = [await make_staff(db, "teacher", ["Янги шахар"], f"+7705222801{i}", f"Половина Ставки {i}") for i in range(3)]
    rooms = list(await db.scalars(select(Room).where(Room.branch_id == bid).order_by(Room.id)))
    rooms[1].teacher_rate = 3500
    ele = await level_id(db, "ELE")
    (await db.get(Level, ele)).name = "Elementary"
    await db.flush()
    await plan.seed(db)  # the level has a plan: an individual lesson is saved without picking a row
    lessons = []
    for i, (room, lvl_rate) in enumerate(((rooms[0], None), (rooms[1], None), (rooms[2], 5000))):
        lvl, teacher = ele, teachers[i]
        if lvl_rate:
            lvl = await level_id(db, "PRE")
            (await db.get(Level, lvl)).teacher_rate = lvl_rate
            await db.flush()
        g = (await client.post("/api/groups", headers=owner_h, json={
            "name": f"Индив П{i}", "branch_id": bid, "level_id": lvl, "teacher_id": teacher.id,
            "room_id": room.id, "kind": "individual"})).json()
        s = await _student(db, client, owner_h, bid, f"Не Пришёл {i}", f"+7705222802{i}")
        await client.post(f"/api/groups/{g['id']}/members", headers=owner_h, json={"student_id": s["id"]})
        lesson = await _lesson_now(db, g, teacher, room)
        lessons.append((lesson.id, s["id"]))

    async def paid(lid):
        a = await db.scalar(select(Accrual).where(Accrual.kind == "lesson", Accrual.ref_id == lid))
        await db.refresh(a)
        return a

    got = []
    for lid, sid in lessons:
        ro = (await client.get(f"/api/lessons/{lid}/attendance", headers=owner_h)).json()
        assert ro["plan_required"] is False
        r = await client.put(f"/api/lessons/{lid}/attendance", headers=owner_h,
                             json={"marks": [{"student_id": sid, "status": "absent"}], "reason": "позже"})
        assert r.status_code == 200, r.text
        got.append((await paid(lid)).amount)
    assert got == [1000, 1750, 2500]

    # the lessons counted before the rule: a fixed 1000 each
    for lid, _ in lessons:
        (await paid(lid)).amount = 1000
    await db.commit()
    pre = await recalc_noshow(db, False)
    assert pre["lessons"] == 3 and pre["changed"] == 2 and pre["diff"] == 2250 and pre["applied"] is False
    assert [(await paid(lid)).amount for lid, _ in lessons] == [1000, 1000, 1000]
    done = await recalc_noshow(db, True)
    assert done["diff"] == 2250 and done["by_teacher"] == {"Половина Ставки 1": 750, "Половина Ставки 2": 1500}
    assert [(await paid(lid)).amount for lid, _ in lessons] == [1000, 1750, 2500]
    assert (await recalc_noshow(db, False))["changed"] == 0


async def test_student_who_left_is_at_once_a_card_in_the_return_funnel(client, db, owner_h):
    from app.models import Lead, LeadStage, Student
    from app.services import retention
    from tests.conftest import branch_id
    from tests.test_core_learning import _student

    bid = await branch_id(db, "Янги шахар")

    async def card(sid):
        rows = list(await db.scalars(select(Lead).where(Lead.student_id == sid).order_by(Lead.id)))
        for x in rows:
            await db.refresh(x)
        return [((await db.get(LeadStage, x.stage_id)).code, x.archived_at is None) for x in rows]

    a = (await _student(db, client, owner_h, bid, "Ушёл Просто", "+77052229001"))["id"]
    b = (await _student(db, client, owner_h, bid, "Ушёл Вернётся", "+77052229002"))["id"]
    c = (await _student(db, client, owner_h, bid, "Ушёл Давно", "+77052229003"))["id"]
    url = "/api/students/{}/leave-decision"
    assert (await client.post(url.format(a), headers=owner_h, json={"left": True, "reason": "переезд"})).status_code == 200
    r = await client.post(url.format(b), headers=owner_h, json={
        "left": True, "reason": "каникулы", "return_on": str((now() + timedelta(days=20)).date())})
    assert r.status_code == 200, r.text
    assert await card(a) == [("left", True)] and await card(b) == [("agreed", True)]
    # the card is on the board of the funnel and is moved like a lead
    board = (await client.get(f"/api/crm/board?pipeline=return&branch_id={bid}", headers=owner_h)).json()
    names = [x["full_name"] for col in board["columns"] for x in col["leads"]]
    assert "Ушёл Просто" in names and "Ушёл Вернётся" in names
    # a reason typed again does not make a second card
    assert (await client.post(url.format(a), headers=owner_h, json={"left": True, "reason": "переезд в Алматы"})).status_code == 200
    assert await card(a) == [("left", True)]
    # stays after all: the card leaves the funnel; leaves again: a new one
    assert (await client.post(url.format(a), headers=owner_h, json={"left": False, "reason": "передумал"})).status_code == 200
    assert await card(a) == [("left", False)]
    assert (await client.post(url.format(a), headers=owner_h, json={"left": True, "reason": "всё же ушёл"})).status_code == 200
    assert await card(a) == [("left", False), ("left", True)]

    # those who left before the funnel: preview changes nothing, the fix makes the cards once
    st = await db.get(Student, c)
    st.status, st.left_at, st.leave_reason = "left", now() - timedelta(days=10), "дорого"
    await db.commit()
    pre = await retention.left_to_funnel(db, False)
    assert pre["left"] == 3 and pre["new"] == 1 and pre["had_card"] == 2 and pre["applied"] is False
    assert await card(c) == []
    done = await retention.left_to_funnel(db, True)
    assert done["new"] == 1 and "дорого" in done["lines"][0] and await card(c) == [("left", True)]
    assert (await retention.left_to_funnel(db, False))["new"] == 0


async def test_reports_of_managers_and_teachers_for_administrators(client, db, owner_h):
    from app.models import Accrual
    from app.services.clock import today
    from tests.conftest import branch_id
    from tests.test_core_learning import _lesson_now, _setup, _student

    bid, teacher, room, g = await _setup(db, client, owner_h)
    s = await _student(db, client, owner_h, bid, "Отчёт Ученик", "+77052229101")
    await client.post(f"/api/groups/{g['id']}/members", headers=owner_h, json={"student_id": s["id"]})
    lesson = await _lesson_now(db, g, teacher, room)
    r = await client.put(f"/api/lessons/{lesson.id}/attendance", headers=owner_h,
                         json={"marks": [{"student_id": s["id"], "status": "present"}], "reason": "позже"})
    assert r.status_code == 200, r.text
    rep = (await client.get("/api/reports/teachers", headers=owner_h)).json()
    row = next(x for x in rep["rows"] if x["user_id"] == teacher.id)
    paid = await db.scalar(select(Accrual.amount).where(Accrual.kind == "lesson", Accrual.ref_id == lesson.id))
    assert row["planned"] == 1 and row["held"] == 1 and row["held_pct"] == 100 and row["attendance_pct"] == 100
    assert row["pay_lessons"] == paid == row["pay_total"] and rep["total"]["held"] == 1
    one = (await client.get(f"/api/reports/teachers?teacher_id={teacher.id}", headers=owner_h)).json()
    assert len(one["rows"]) == 1 and len(one["people"]) >= 1
    old = (await client.get("/api/reports/teachers?date_from=2026-01-01&date_to=2026-01-31", headers=owner_h)).json()
    assert old["rows"] == []

    sales = await make_staff(db, "sales", ["Янги шахар"], "+77052229102", "Отчёт Менеджер")
    h = await login(client, "+77052229102")
    lead = (await client.post("/api/crm/leads", headers=h, json={"full_name": "Лид Отчёта", "branch_id": bid, "phone": "+77052229103"})).json()
    r = await client.post(f"/api/crm/leads/{lead['id']}/events", headers=h, json={"kind": "call", "text": "позвонил", "result": "thinking"})
    assert r.status_code in (200, 201), r.text
    rep = (await client.get(f"/api/reports/managers?date_from={today()}&date_to={today()}", headers=owner_h)).json()
    row = next(x for x in rep["rows"] if x["user_id"] == sales.id)
    assert row["new"] == 1 and row["worked"] == 1 and row["actions"] == 1 and row["paid"] == 0 and row["conversion"] == 0
    assert (await client.get(f"/api/reports/managers?manager_id={sales.id}", headers=owner_h)).json()["total"]["new"] == 1
    x = await client.get("/api/reports/managers.xlsx", headers=owner_h)
    assert x.status_code == 200 and x.content[:2] == b"PK"
    # not for a manager or a teacher
    assert (await client.get("/api/reports/managers", headers=h)).status_code == 403
    assert (await client.get("/api/reports/teachers", headers=h)).status_code == 403
