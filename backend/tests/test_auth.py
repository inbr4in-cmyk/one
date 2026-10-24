import pyotp
from sqlalchemy import text

from app.core.kv import get_kv
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


async def test_wrong_password_locks_after_five(client, owner):
    for _ in range(5):
        r = await client.post("/api/auth/login", json={"phone": owner.phone, "password": "nope"})
        assert r.status_code == 401
    r = await client.post("/api/auth/login", json={"phone": owner.phone, "password": PASSWORD})
    assert r.status_code == 423


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
    # Replaying the old token kills the session: the new token stops working too.
    assert (await client.post("/api/auth/refresh", json={"refresh_token": first}, headers={"X-Client": "mobile"})).status_code == 401
    assert (await client.post("/api/auth/refresh", json={"refresh_token": second}, headers={"X-Client": "mobile"})).status_code == 401


async def test_cookie_refresh_requires_csrf_header(client, owner):
    await client.post("/api/auth/login", json={"phone": owner.phone, "password": PASSWORD})
    assert "oe_refresh" in client.cookies
    assert (await client.post("/api/auth/refresh")).status_code == 403
    r = await client.post("/api/auth/refresh", headers={"X-Requested-With": "one-english"})
    assert r.status_code == 200 and r.json()["access_token"]


async def test_totp_flow(client, owner):
    h = await login(client, owner.phone)
    setup = (await client.post("/api/auth/2fa/setup", headers=h)).json()
    code = pyotp.TOTP(setup["secret"]).now()
    r = await client.post("/api/auth/2fa/enable", json={"code": code}, headers=h)
    assert r.status_code == 200
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
