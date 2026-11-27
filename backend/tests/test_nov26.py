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
