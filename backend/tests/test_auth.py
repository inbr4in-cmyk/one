import pyotp
from sqlalchemy import text

from httpx import ASGITransport, AsyncClient

from app.core.kv import get_kv
from app.main import app
from tests.conftest import PASSWORD, login


async def test_login_me_logout(client, owner):
    h = await login(client, "8 701 000 00 01")  # normalized to +77010000001
    me = (await client.get("/api/auth/me", headers=h)).json()
    assert me["full_name"] == "Айгерим Владелец"
    assert "owner" in me["roles"]
    assert me["permissions"]["finance.view"] == "network"
    assert (await client.post("/api/auth/logout", headers=h)).status_code == 204
    # The session is dead immediately, even though the JWT has not expired.
    assert (await client.get("/api/auth/me", headers=h)).status_code == 401


async def test_wrong_passwords_slow_down_unknown_ip_but_never_lock_known_one(client, owner):
    """QA B-4: five wrong passwords make that phone + IP wait; they don't lock the account."""
    for _ in range(5):
        r = await client.post("/api/auth/login", json={"phone": owner.phone, "password": "nope"})
        assert r.status_code == 401
    # This IP never had a session for the owner: even the right password waits (no oracle for the attacker).
    r = await client.post("/api/auth/login", json={"phone": owner.phone, "password": PASSWORD})
    assert r.status_code == 429 and int(r.headers["Retry-After"]) > 0
    # The owner from another IP is not affected at all.
    async with AsyncClient(transport=ASGITransport(app=app, client=("10.0.0.7", 1234)), base_url="http://test") as other:
        r = await other.post("/api/auth/login", json={"phone": owner.phone, "password": PASSWORD})
        assert r.status_code == 200, r.text
        device = r.cookies.get("oe_device")
    assert device
    # A device that signed in before gets in with the right password even from the throttled IP.
    client.cookies.set("oe_device", device, path="/api/auth")
    r = await client.post("/api/auth/login", json={"phone": owner.phone, "password": PASSWORD})
    assert r.status_code == 200, r.text


async def test_known_ip_gets_in_after_failures_and_owners_hear_of_burst(client, db, owner):
    from sqlalchemy import select

    from app.models import Notification

    await login(client, owner.phone)  # this IP is now known for the owner
    client.cookies.clear()
    for _ in range(10):
        await client.post("/api/auth/login", json={"phone": owner.phone, "password": "nope"})
    r = await client.post("/api/auth/login", json={"phone": owner.phone, "password": PASSWORD})
    assert r.status_code == 200, r.text
    alerts = (await db.scalars(select(Notification).where(Notification.user_id == owner.id, Notification.kind == "security"))).all()
    assert len(alerts) == 1


async def test_refresh_reuse_within_grace_returns_same_pair(client, owner):
    """QA C-6: two tabs refreshing with one token both stay signed in."""
    r = await client.post("/api/auth/login", json={"phone": owner.phone, "password": PASSWORD}, headers={"X-Client": "mobile"})
    first = r.json()["refresh_token"]
    a = await client.post("/api/auth/refresh", json={"refresh_token": first}, headers={"X-Client": "mobile"})
    b = await client.post("/api/auth/refresh", json={"refresh_token": first}, headers={"X-Client": "mobile"})
    assert a.status_code == b.status_code == 200
    assert a.json()["refresh_token"] == b.json()["refresh_token"]
    me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {b.json()['access_token']}"})
    assert me.status_code == 200
    # After the grace window the old token is theft again: the session is revoked.
    get_kv().clear()
    c = await client.post("/api/auth/refresh", json={"refresh_token": first}, headers={"X-Client": "mobile"})
    assert c.status_code == 401


async def test_unknown_user_same_error(client, owner):
    r = await client.post("/api/auth/login", json={"phone": "+77779999999", "password": "x"})
    assert r.status_code == 401
    assert r.json()["detail"] == "Неверный телефон или пароль"


async def test_refresh_rotation_and_reuse_detection(client, owner):
    r = await client.post("/api/auth/login", json={"phone": owner.phone, "password": PASSWORD},
                          headers={"X-Client": "mobile"})
    first = r.json()["refresh_token"]
    r2 = await client.post("/api/auth/refresh", json={"refresh_token": first}, headers={"X-Client": "mobile"})
    assert r2.status_code == 200
    second = r2.json()["refresh_token"]
    assert second != first
    # Replaying the old token after the short grace window kills the session: the new token stops working too.
    get_kv().clear()
    assert (await client.post("/api/auth/refresh", json={"refresh_token": first}, headers={"X-Client": "mobile"})).status_code == 401
    assert (await client.post("/api/auth/refresh", json={"refresh_token": second}, headers={"X-Client": "mobile"})).status_code == 401


async def test_cookie_refresh_requires_csrf_header(client, owner):
    await client.post("/api/auth/login", json={"phone": owner.phone, "password": PASSWORD})
    assert "oe_refresh" in client.cookies
    assert (await client.post("/api/auth/refresh")).status_code == 403
    r = await client.post("/api/auth/refresh", headers={"X-Requested-With": "one-english"})
    assert r.status_code == 200 and r.json()["access_token"]


async def test_totp_flow(client, db, owner):
    h = await login(client, owner.phone)
    # QA H-5: the password is asked again before an authenticator is attached.
    assert (await client.post("/api/auth/2fa/setup", headers=h)).status_code == 400
    assert (await client.post("/api/auth/2fa/setup", headers=h, json={"password": "wrong-pass-1"})).status_code == 400
    setup = (await client.post("/api/auth/2fa/setup", headers=h, json={"password": PASSWORD})).json()
    code = pyotp.TOTP(setup["secret"]).now()
    r = await client.post("/api/auth/2fa/enable", json={"code": code}, headers=h)
    assert r.status_code == 200
    stored = (await db.execute(text("SELECT totp_secret FROM users WHERE id = :i"), {"i": owner.id})).scalar()
    assert stored.startswith("enc1:") and setup["secret"] not in stored
    # Old session revoked after enabling 2FA
    assert (await client.get("/api/auth/me", headers=h)).status_code == 401
    r = await client.post("/api/auth/login", json={"phone": owner.phone, "password": PASSWORD})
    assert r.json()["mfa_required"] is True and r.json()["access_token"] is None
    tok = r.json()["mfa_token"]
    assert (await client.post("/api/auth/mfa", json={"mfa_token": tok, "code": "000000"})).status_code == 401
    get_kv().clear()  # same code was just used by /2fa/enable flow in this window
    r = await client.post("/api/auth/mfa", json={"mfa_token": tok, "code": pyotp.TOTP(setup["secret"]).now()})
    assert r.status_code == 200
    me = (await client.get("/api/auth/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"})).json()
    assert me["mfa"] is True


async def test_sensitive_module_needs_mfa(client, owner, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "require_staff_2fa", True)
    h = await login(client, owner.phone)
    r = await client.get("/api/audit", headers=h)
    assert r.status_code == 403


async def test_audit_log_is_append_only(db, client, owner):
    await login(client, owner.phone)
    import pytest
    from sqlalchemy.exc import DBAPIError

    with pytest.raises(DBAPIError):
        async with db.begin_nested():
            await db.execute(text("DELETE FROM audit_log"))
    with pytest.raises(DBAPIError):
        async with db.begin_nested():
            await db.execute(text("UPDATE audit_log SET action='x'"))


async def test_otp_login_for_parent(client, db):
    from app.models import User

    u = User(kind="parent", full_name="Мама", phone="+77015550000")
    db.add(u)
    await db.flush()
    assert (await client.post("/api/auth/otp/request", json={"phone": "+77015550000"})).status_code == 204
    # Unknown phones get the same answer
    assert (await client.post("/api/auth/otp/request", json={"phone": "+77015559999"})).status_code == 204
    from app.core.security import sha256

    stored = await get_kv().get("otp:+77015550000")
    assert stored and len(stored) == 64
    # We can't read the code (only its hash is stored); brute-force guard: 5 wrong tries burn it.
    for _ in range(5):
        r = await client.post("/api/auth/otp/verify", json={"phone": "+77015550000", "code": "999999"})
        assert r.status_code == 401
    assert sha256("999999") != stored
    r = await client.post("/api/auth/otp/verify", json={"phone": "+77015550000", "code": "999999"})
    assert r.status_code == 401
    assert await get_kv().get("otp:+77015550000") is None  # burnt after the 6th try
