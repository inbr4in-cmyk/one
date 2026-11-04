"""Regression tests for the second QA round (report of 2026-11-04): every High and Medium backend finding."""

import io
import zipfile
from datetime import time, timedelta

from sqlalchemy import select

from app import jobs
from app.models import Accrual, Attempt, Freeze, Lead, Notification, Payment, Question, Student, Test
from app.services import realtime
from app.services.clock import at_local, now, today
from tests.conftest import PASSWORD, branch_id, level_id, login, make_staff
from tests.test_chats import PNG, _portal_login, _world
from tests.test_core_learning import _student

YANGI, SEVER = "Янги шахар", "Север"


async def _pay(client, h, sid, lessons=8, key=None):
    headers = {**h, **({"Idempotency-Key": key} if key else {})}
    return await client.post("/api/payments", headers=headers, json={"student_id": sid, "lessons": lessons, "method": "cash"})


# ---------- B-2: «today» payments ----------
async def test_b2_payment_period_is_inclusive_in_school_time(db, client, owner_h):
    y = await branch_id(db, YANGI)
    st = await _student(db, client, owner_h, y)
    p = (await _pay(client, owner_h, st["id"])).json()
    d = today()
    r = await client.get(f"/api/payments?date_from={d}&date_to={d}&branch_id={y}", headers=owner_h)
    assert r.status_code == 200 and [x["id"] for x in r.json()["items"]] == [p["id"]]
    # 00:30 school time is the previous evening in UTC — still «today»; 23:30 yesterday is not.
    row = await db.get(Payment, p["id"])
    row.paid_at = at_local(d, time(0, 30))
    await db.flush()
    assert (await client.get(f"/api/payments?date_from={d}&date_to={d}", headers=owner_h)).json()["total"] == 1
    row.paid_at = at_local(d - timedelta(days=1), time(23, 30))
    await db.flush()
    assert (await client.get(f"/api/payments?date_from={d}&date_to={d}", headers=owner_h)).json()["total"] == 0
    # An ISO datetime from an older client is read as that school day.
    assert (await client.get(f"/api/payments?date_from={d - timedelta(days=1)}T00:00:00&date_to={d}", headers=owner_h)
            ).json()["total"] == 1


# ---------- B-3: refunds ----------
async def test_b3_refund_capped_by_lessons_left_from_payment(db, client, owner_h):
    y = await branch_id(db, YANGI)
    st = await _student(db, client, owner_h, y)
    first = (await _pay(client, owner_h, st["id"], 8)).json()
    second = (await _pay(client, owner_h, st["id"], 4, key="second-payment-01")).json()
    s = await db.get(Student, st["id"])
    assert s.lessons_left == 12
    s.lessons_left, s.lessons_done = 10, 2  # two lessons held: they came out of the first (oldest) payment
    await db.flush()
    lim = (await client.get(f"/api/payments/{first['id']}/refundable", headers=owner_h)).json()
    assert lim["lessons_max"] == 6
    bad = [({"lessons": 0, "amount": 0}, "Укажите"), ({"lessons": 15, "amount": 1}, "осталось только 6"),
           ({"lessons": 0, "amount": 1000}, "без уроков"), ({"lessons": 1, "amount": 24000}, "не больше 3000")]
    for body, msg in bad:
        r = await client.post(f"/api/payments/{first['id']}/refund", headers=owner_h, json={**body, "reason": "проверка"})
        assert r.status_code == 400 and msg in r.json()["detail"], (body, r.text)
    r = await client.post(f"/api/payments/{first['id']}/refund", headers=owner_h, json={"lessons": 6, "amount": 18000, "reason": "Переезд"})
    assert r.status_code == 201 and r.json()["full"] is False
    await db.refresh(s)
    assert s.lessons_left == 4  # the second payment's lessons are untouched
    r = await client.post(f"/api/payments/{second['id']}/refund", headers=owner_h, json={"lessons": 5, "amount": 1, "reason": "x-x-x"})
    assert r.status_code == 400


async def test_b3_bonus_reversal_proportional_then_full(db, client, owner_h):
    y = await branch_id(db, YANGI)
    office = await make_staff(db, "office_manager", [YANGI], "+77020000301", "Офис")
    st = await _student(db, client, owner_h, y)
    p = (await _pay(client, owner_h, st["id"], 8)).json()
    a = Accrual(user_id=office.id, kind="sale", amount=2000, ref_type="payment", ref_id=p["id"], period="2026-11",
                branch_id=y, description="Продажа")
    db.add(a)
    await db.flush()

    async def reversed_total():
        rows = await db.scalars(select(Accrual.amount).where(Accrual.kind == "reversal", Accrual.ref_id == a.id))
        return -sum(rows)

    r = await client.post(f"/api/payments/{p['id']}/refund", headers=owner_h, json={"lessons": 2, "amount": 6000, "reason": "часть"})
    assert r.status_code == 201, r.text
    assert await reversed_total() == 500  # 6000 of 24000 → a quarter of the bonus
    r = await client.post(f"/api/payments/{p['id']}/refund", headers=owner_h, json={"lessons": 6, "amount": 18000, "reason": "всё"})
    assert r.json()["full"] is True
    assert await reversed_total() == 2000  # never more than the bonus itself


# ---------- B-4 is in test_auth.py ----------

# ---------- B-5: freezes ----------
async def test_b5_freeze_rules_and_nightly_end(db, client, owner_h):
    y = await branch_id(db, YANGI)
    st = await _student(db, client, owner_h, y)
    d = today()
    body = {"starts_on": str(d), "ends_on": str(d + timedelta(days=7))}
    r = await client.post(f"/api/students/{st['id']}/freeze", headers=owner_h, json=body)
    assert r.status_code == 400 and "предоплате" in r.json()["detail"]  # rules p.362: a month prepaid
    await _pay(client, owner_h, st["id"], 12)
    r = await client.post(f"/api/students/{st['id']}/freeze", headers=owner_h,
                          json={"starts_on": "2020-01-01", "ends_on": "2020-01-08"})
    assert r.status_code == 400 and "прошлом" in r.json()["detail"]
    r = await client.post(f"/api/students/{st['id']}/freeze", headers=owner_h, json=body)
    assert r.status_code == 200 and r.json()["status"] == "frozen"
    # The freeze ran out (dates moved back) — the nightly job brings the student back.
    f = await db.scalar(select(Freeze).where(Freeze.student_id == st["id"]))
    f.starts_on, f.ends_on = d - timedelta(days=8), d - timedelta(days=1)
    await db.flush()
    out = await jobs.sync_freezes(db)
    assert out["unfrozen"] == 1 and (await db.get(Student, st["id"])).status == "active"
    # A freeze that starts in the future switches the status on its first day.
    f.starts_on, f.ends_on, f.ended_early_on = d, d + timedelta(days=5), None
    await db.flush()
    assert (await jobs.sync_freezes(db))["frozen"] == 1


async def test_b5_unfreeze_allowed_while_frozen_even_after_end(db, client, owner_h):
    y = await branch_id(db, YANGI)
    st = await _student(db, client, owner_h, y)
    s = await db.get(Student, st["id"])
    s.status = "frozen"  # stuck from before the nightly job existed
    db.add(Freeze(student_id=s.id, starts_on=today() - timedelta(days=9), ends_on=today() - timedelta(days=2),
                  created_by=await _owner_id(db)))
    await db.flush()
    r = await client.post(f"/api/students/{st['id']}/unfreeze", headers=owner_h)
    assert r.status_code == 200 and r.json()["status"] == "active"
    assert (await client.post(f"/api/students/{st['id']}/unfreeze", headers=owner_h)).status_code == 400


async def _owner_id(db):
    from app.models import User

    return await db.scalar(select(User.id).where(User.phone == "+77010000001"))


# ---------- C-1: idempotent payments ----------
async def test_c1_same_idempotency_key_pays_once(db, client, owner_h):
    y = await branch_id(db, YANGI)
    st = await _student(db, client, owner_h, y)
    r1 = await _pay(client, owner_h, st["id"], 8, key="form-7f3a-0001")
    r2 = await _pay(client, owner_h, st["id"], 8, key="form-7f3a-0001")  # a retry after a timeout
    assert (r1.status_code, r2.status_code) == (201, 200)
    assert r1.json()["id"] == r2.json()["id"]
    assert (await db.get(Student, st["id"])).lessons_left == 8
    # Two requests that slipped past the check at the same moment still meet the unique index.
    from sqlalchemy.exc import IntegrityError

    dup = await db.get(Payment, r1.json()["id"])
    try:
        async with db.begin_nested():
            db.add(Payment(student_id=dup.student_id, branch_id=dup.branch_id, amount=1, lessons=1, lesson_price=1,
                           method="cash", received_by=dup.received_by, paid_at=now(), idempotency_key="form-7f3a-0001"))
            await db.flush()
        raise AssertionError("unique index missing")
    except IntegrityError:
        pass
    # Without a key, an identical payment right after is a double tap.
    assert (await _pay(client, owner_h, st["id"], 4)).status_code == 201
    assert (await _pay(client, owner_h, st["id"], 4)).status_code == 409
    assert (await _pay(client, owner_h, st["id"], 8, key="bad key!")).status_code == 400


# ---------- C-2: public placement test ----------
async def _placement(db, client, owner_h, bid):
    t = Test(kind="placement", title="Тест", max_score=3, is_published=True, time_limit_min=30,
             scale=[{"min": 0, "level_id": await level_id(db, "BEG")}, {"min": 2, "level_id": await level_id(db, "ELE")}])
    db.add(t)
    await db.flush()
    for i in range(3):
        db.add(Question(test_id=t.id, order=i, kind="single", text=f"Q{i}", options=["a", "b"], correct=[1], points=1))
    await db.flush()
    token = (await client.get(f"/api/branches/{bid}/qr", headers=owner_h)).json()["token"]
    qs = (await client.get(f"/api/public/placement/{token}")).json()["questions"]
    return token, qs


async def test_c2_placement_rejects_junk_and_keeps_other_branch_lead(db, client, owner_h):
    y, s = await branch_id(db, YANGI), await branch_id(db, SEVER)
    other = (await client.post("/api/crm/leads", headers=owner_h, json={
        "full_name": "Лид Север", "phone": "+77075554433", "branch_id": s, "level_id": await level_id(db, "UPP")})).json()
    token, qs = await _placement(db, client, owner_h, y)

    async def start():
        return (await client.post(f"/api/public/placement/{token}/start",
                                  json={"name": "Тимур", "phone": "87075554433", "consent": True})).json()

    st = await start()
    for junk in ([[1]], {"1": [[1]]}, {"x": 1}, {str(i): 1 for i in range(400)}, {"1": "a" * 3000}):
        r = await client.post("/api/public/placement/submit", json={"attempt_token": st["attempt_token"], "answers": junk})
        assert r.status_code == 422, (junk if len(str(junk)) < 50 else "big", r.status_code)
    answers = {str(q["id"]): [1] for q in qs[:2]}
    assert (await client.post("/api/public/placement/submit", json={"attempt_token": st["attempt_token"], "answers": answers})
            ).status_code == 200
    lead_s = await db.get(Lead, other["id"])
    assert lead_s.branch_id == s and lead_s.level_id == await level_id(db, "UPP") and lead_s.placement_score is None
    mine = await db.scalar(select(Lead).where(Lead.branch_id == y, Lead.source == "qr"))
    assert mine is not None and mine.placement_score == 2
    # A second attempt with the same phone doesn't overwrite the level already on the card.
    st2 = await start()
    await client.post("/api/public/placement/submit", json={"attempt_token": st2["attempt_token"], "answers": {}})
    await db.refresh(mine)
    assert mine.placement_score == 2 and mine.level_id == await level_id(db, "ELE")
    # Server time: an attempt past the limit is refused.
    st3 = await start()
    a = await db.get(Attempt, st3["attempt_id"])
    a.started_at = now() - timedelta(minutes=40)
    await db.flush()
    r = await client.post("/api/public/placement/submit", json={"attempt_token": st3["attempt_token"], "answers": answers})
    assert r.status_code == 400 and "истекло" in r.json()["detail"]


# ---------- C-3: blocked student ----------
async def test_c3_blocked_student_cannot_chat_or_upload_parent_still_can(db, client, owner_h):
    _, teacher, g, (a, _) = await _world(db, client, owner_h)
    tid = teacher.id
    db.expunge(teacher)  # let the API load the account with its roles, as in a real request
    sa = await _portal_login(db, client, a["user_id"])
    pa = await _portal_login(db, client, a["guardians"][0]["user_id"])
    chat = (await client.get("/api/chats", headers=sa)).json()[0]
    st = await db.get(Student, a["id"])
    st.access_blocked_at = now()
    await db.flush()
    r = await client.post(f"/api/chats/{chat['id']}/messages", headers=sa, json={"text": "привет"})
    assert r.status_code == 403 and "оплаты" in r.json()["detail"]
    r = await client.post("/api/files", headers=sa, files={"file": ("a.png", PNG, "image/png")})
    assert r.status_code == 403
    assert (await client.get(f"/api/chats/{chat['id']}/messages", headers=sa)).status_code == 200  # reading stays
    assert (await client.get(f"/api/portal/students/{a['id']}/payments", headers=pa)).status_code == 200
    direct = (await client.post("/api/chats/direct", headers=pa, json={"user_id": tid})).json()
    assert (await client.post(f"/api/chats/{direct['id']}/messages", headers=pa, json={"text": "Оплатим завтра"})).status_code == 201


# ---------- C-4 and H-13: search ----------
async def test_c4_h13_search_hides_phones_and_escapes_wildcards(db, client, owner_h):
    y = await branch_id(db, YANGI)
    await client.post("/api/crm/leads", headers=owner_h, json={"full_name": "Гонка", "phone": "+77071112244", "branch_id": y})
    smm = await make_staff(db, "smm", [YANGI], "+77020000302", "SMM")
    sh = await login(client, smm.phone)
    assert (await client.get("/api/search?q=1112244", headers=sh)).json()["leads"] == []
    assert len((await client.get("/api/search?q=Гонка", headers=sh)).json()["leads"]) == 1
    assert len((await client.get("/api/search?q=1112244", headers=owner_h)).json()["leads"]) == 1
    r = await client.get("/api/search?q=%25%25%25%25", headers=owner_h)
    assert r.status_code == 200 and all(v == [] for v in r.json().values())
    assert (await client.get("/api/students?q=%25_", headers=owner_h)).json()["total"] == 0


# ---------- C-5: websockets ----------
async def test_c5_logout_and_password_change_end_sockets(db, client, owner):
    realtime.sent.clear()
    h = await login(client, owner.phone)
    sid = (await client.get("/api/auth/sessions", headers=h)).json()[0]["id"]
    await client.post("/api/auth/logout", headers=h)
    ev = [e for ch, e in realtime.sent if ch == f"user:{owner.id}" and e["type"] == "session.ended"]
    assert ev and realtime.ends_session(ev[-1], sid)
    h = await login(client, owner.phone)
    keep = next(x["id"] for x in (await client.get("/api/auth/sessions", headers=h)).json() if x["current"])
    r = await client.post("/api/auth/password", headers=h, json={"old_password": PASSWORD, "new_password": "Brand-new-pass-77"})
    assert r.status_code == 204
    ev = [e for ch, e in realtime.sent if e["type"] == "session.ended"][-1]
    assert not realtime.ends_session(ev, keep) and realtime.ends_session(ev, keep + 1000)


# ---------- C-7: junk input ----------
async def test_c7_junk_input_is_4xx_not_500(db, client, owner_h):
    assert (await client.get("/api/students/99999999999999999999", headers=owner_h)).status_code == 422
    assert (await client.get("/api/students?q=%00", headers=owner_h)).status_code == 422
    assert (await client.get("/api/notifications?limit=-1", headers=owner_h)).status_code == 422
    assert (await client.get("/api/groups/99999", headers=owner_h)).json()["detail"] == "Группа не найдена"  # H-8
    y = await branch_id(db, YANGI)
    r = await client.post("/api/crm/leads", headers=owner_h, json={"full_name": "Имя", "parent_name": "x" * 300, "branch_id": y})
    assert r.status_code == 422
    r = await client.post("/api/crm/leads", headers=owner_h, json={"full_name": "Имя\u0000", "branch_id": y})
    assert r.status_code == 422
    r = await client.post("/api/payments", headers=owner_h, json={"student_id": 1, "lessons": 1, "method": "cash",
                                                                   "promo_code": "P" * 100})
    assert r.status_code == 422


async def test_c7_database_errors_map_by_sqlstate(client):
    """Errors only the database sees (value too long, unique race) are 422 / 409, never 500."""
    from fastapi import APIRouter
    from sqlalchemy.exc import DBAPIError

    from app.main import app

    class PgErr(Exception):
        def __init__(self, state):
            self.sqlstate = state

    router = APIRouter()
    for state in ("22001", "23505", "XX000"):
        async def boom(state=state):
            raise DBAPIError("INSERT …", {}, PgErr(state))

        router.add_api_route(f"/api/_qa2/{state}", boom)
    app.include_router(router)
    assert (await client.get("/api/_qa2/22001")).status_code == 422
    assert (await client.get("/api/_qa2/23505")).status_code == 409
    assert (await client.get("/api/_qa2/XX000")).status_code == 500


# ---------- C-8: own password ----------
async def test_c8_own_password_needs_old_one_and_policy(db, client, owner, owner_h):
    r = await client.post(f"/api/staff/{owner.id}/password", headers=owner_h, json={"password": "Totally-new-77"})
    assert r.status_code == 400 and "Текущий" in r.json()["detail"]
    for weak in ("qwerty12345", "Password123!", "a" * 257 + "1"):
        r = await client.post(f"/api/staff/{owner.id}/password", headers=owner_h, json={"password": weak, "old_password": PASSWORD})
        assert r.status_code in (400, 422), weak
    r = await client.post(f"/api/staff/{owner.id}/password", headers=owner_h,
                          json={"password": "Totally-new-77", "old_password": PASSWORD})
    assert r.status_code == 204
    assert (await client.get("/api/auth/me", headers=owner_h)).status_code == 200  # this session stays


# ---------- C-9: webhook ----------
async def test_c9_bad_meta_entries_dont_drop_the_batch(db, client, monkeypatch):
    from app.modules.inbox import router as inbox_router

    monkeypatch.setattr(inbox_router.meta, "verify_signature", lambda body, sig: True)
    good = {"from": "77015550011", "id": "wamid.ok1", "timestamp": "1762250000", "type": "text", "text": {"body": "Здравствуйте"}}
    for payload in ([1, 2, 3], {"object": "whatsapp_business_account", "entry": [1, {"changes": "x"},
                    {"changes": [{"value": {"messages": [{"type": "text", "text": "not-a-dict"}, good]}}]}]}):
        r = await client.post("/api/webhooks/meta", json=payload)
        assert r.status_code == 200, r.text
    assert r.json()["stored"] == 1


# ---------- C-10: phones in student chats ----------
async def test_c10_spelled_and_spaced_phone_numbers_blocked(db, client, owner_h):
    _, _, _, (a, _) = await _world(db, client, owner_h)
    sa = await _portal_login(db, client, a["user_id"])
    chat = (await client.get("/api/chats", headers=sa)).json()[0]
    for text in ("звони 8 7 0 1 2 3 4 5 6 7 8", "восемь семь ноль один два три четыре пять шесть семь восемь",
                 "+7 (701) 234-56-78"):
        r = await client.post(f"/api/chats/{chat['id']}/messages", headers=sa, json={"text": text})
        assert r.status_code == 400, text
    r = await client.post(f"/api/chats/{chat['id']}/messages", headers=sa, json={"text": "hi", "file_name": "мой номер 87012345678"})
    assert r.status_code == 400
    ok = await client.post(f"/api/chats/{chat['id']}/messages", headers=sa, json={"text": "В 2024 году 5 уроков по 3000"})
    assert ok.status_code == 201


# ---------- C-11: uploads ----------
async def test_c11_content_sniffing_and_download_name(db, client, owner_h, tmp_path, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "storage_dir", str(tmp_path))
    docx = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    r = await client.post("/api/files", headers=owner_h, files={"file": ("x.jpg", b"<b>" + b"\xff\xd8\xff" * 5, "image/jpeg")})
    assert r.status_code == 400
    r = await client.post("/api/files", headers=owner_h, files={"file": ("x.docx", b"MZ\x90\x00" + b"\x00" * 100, docx)})
    assert r.status_code == 400
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", "<w:document/>")
    r = await client.post("/api/files", headers=owner_h, files={"file": ("Отчёт.docx", buf.getvalue(), docx)})
    assert r.status_code == 201, r.text
    d = await client.get(r.json()["url"])
    assert d.status_code == 200 and "attachment" in d.headers["content-disposition"] and ".docx" in d.headers["content-disposition"]
    monkeypatch.setattr(get_settings(), "max_upload_mb", 0)
    assert (await client.post("/api/files", headers=owner_h, files={"file": ("a.png", PNG, "image/png")})).status_code == 413


# ---------- C-12: health ----------
async def test_c12_health_reports_dependencies(client, monkeypatch):
    from app.core import kv

    r = await client.get("/api/health")
    assert r.status_code == 200 and r.json() == {"ok": True, "db": True, "redis": True}

    async def down():
        raise ConnectionError("redis down")

    monkeypatch.setattr(kv.get_kv(), "ping", down)
    r = await client.get("/api/health")
    assert r.status_code == 503 and r.json()["redis"] is False


# ---------- H-1, H-2, H-3, H-4 ----------
async def test_h1_about_student_must_belong_to_chat(db, client, owner_h):
    _, teacher, _, (a, b) = await _world(db, client, owner_h)
    tid = teacher.id
    db.expunge(teacher)  # let the API load the account with its roles, as in a real request
    pa = await _portal_login(db, client, a["guardians"][0]["user_id"])
    r = await client.post("/api/chats/direct", headers=pa, json={"user_id": tid, "about_student_id": b["id"]})
    assert r.status_code == 400
    r = await client.post("/api/chats/direct", headers=pa, json={"user_id": tid, "about_student_id": a["id"]})
    assert r.status_code == 200


async def test_h2_h4_shop_branch_and_teacher_top(db, client, owner_h):
    y, s = await branch_id(db, YANGI), await branch_id(db, SEVER)
    _, teacher, g, (a, _) = await _world(db, client, owner_h)
    sa = await _portal_login(db, client, a["user_id"])
    other = (await client.post("/api/shop/items", headers=owner_h, json={"name": "Кружка Север", "price_coins": 1, "stock": 5,
                                                                        "branch_id": s})).json()
    shared = (await client.post("/api/shop/items", headers=owner_h, json={"name": "Ручка", "price_coins": 1, "stock": 5})).json()
    ids = {i["id"] for i in (await client.get("/api/shop/items", headers=sa)).json()}
    assert shared["id"] in ids and other["id"] not in ids
    assert (await client.post("/api/shop/orders", headers=sa, json={"student_id": a["id"], "item_id": other["id"]})).status_code == 404
    # A teacher's leaderboard holds only their own groups.
    outsider = await _student(db, client, owner_h, y, name="Чужой Ученик", phone="+77051119988")
    from app.models import CoinEntry

    for sid in (a["id"], outsider["id"]):
        db.add(CoinEntry(student_id=sid, at=now(), kind="award", delta=10, reason="x"))
    await db.flush()
    th = await login(client, teacher.phone)
    names = [x["name"] for x in (await client.get("/api/coins/top", headers=th)).json()]
    assert names == [a["full_name"]]


async def test_h3_complaint_checks_branch_and_link(db, client, owner_h):
    _, teacher, _, (a, _) = await _world(db, client, owner_h)
    pa = await _portal_login(db, client, a["guardians"][0]["user_id"])
    base = {"subject": "Тема жалобы", "body": "Подробное описание проблемы"}
    r = await client.post("/api/complaints", headers=pa, json={**base, "file_url": "javascript:alert(1)"})
    assert r.status_code == 400
    r = await client.post("/api/complaints", headers=pa, json={**base, "branch_id": await branch_id(db, SEVER)})
    assert r.status_code == 403
    r = await client.post("/api/complaints", headers=pa, json={**base, "file_url": "https://example.com/a.jpg"})
    assert r.status_code == 201 and r.json()["branch_id"] == await branch_id(db, YANGI)


# ---------- H-5 ----------
async def test_h5_notifications_closed_until_2fa(db, client, owner, monkeypatch):
    from app.core.config import get_settings

    h = await login(client, owner.phone)
    monkeypatch.setattr(get_settings(), "require_staff_2fa", True)
    assert (await client.get("/api/notifications", headers=h)).status_code == 403
    assert (await client.get("/api/counters", headers=h)).status_code == 403


# ---------- H-15 ----------
async def test_h15_parallel_lead_creation_gives_one_lead_and_a_conflict(db, client, owner_h):
    y = await branch_id(db, YANGI)
    body = {"full_name": "Дубль", "phone": "+77079990011", "branch_id": y}
    assert (await client.post("/api/crm/leads", headers=owner_h, json=body)).status_code == 201
    assert (await client.post("/api/crm/leads", headers=owner_h, json=body)).status_code == 409
    from sqlalchemy.exc import IntegrityError

    first = await db.scalar(select(Lead).where(Lead.phone == "+77079990011"))
    try:
        async with db.begin_nested():
            db.add(Lead(full_name="Обход", phone="+77079990011", branch_id=y, pipeline_id=first.pipeline_id,
                        stage_id=first.stage_id, stage_changed_at=now(), source="sales"))
            await db.flush()
        raise AssertionError("unique index missing")
    except IntegrityError:
        pass


# ---------- H-16 ----------
async def test_h16_crm_analytics_default_period_uses_school_day(db, client, owner_h):
    r = await client.get("/api/crm/analytics", headers=owner_h)
    assert r.status_code == 200 and r.json()["period"][1] == str(today())


async def test_burst_alert_is_a_notification(db, client, owner):
    # Sanity: the owners' alert from B-4 is stored as a normal notification kind.
    for _ in range(10):
        await client.post("/api/auth/login", json={"phone": owner.phone, "password": "wrong-password-1"})
    assert await db.scalar(select(Notification.id).where(Notification.kind == "security"))
