"""Regression tests for the security review findings."""

import pytest
from sqlalchemy import select

from app.models import Accrual, CoinEntry, Role, UserRole
from tests.conftest import branch_id, level_id, login, make_staff
from tests.test_chats import _portal_login, _world

YANGI, SEVER = "Янги шахар", "Север"


async def _role_user(db, client, owner_h, code, perms, phone, branches=(YANGI,)):
    r = await client.post("/api/roles", headers=owner_h, json={
        "name": code, "code": code, "permissions": [{"module": m, "action": a, "scope": s} for m, a, s in perms]})
    assert r.status_code == 201, r.text
    u = await make_staff(db, "teacher", list(branches), phone, code)
    ur = await db.scalar(select(UserRole).where(UserRole.user_id == u.id))
    ur.role_id = r.json()["id"]
    await db.flush()
    return u


async def test_hr_cannot_take_over_stronger_account(db, client, owner_h):
    hr = await _role_user(db, client, owner_h, "hr", [("staff", "view", "branch"), ("staff", "edit", "branch")], "+77020000080")
    admin = await make_staff(db, "branch_admin", [YANGI], "+77020000081", "Админ")
    t = await make_staff(db, "teacher", [YANGI], "+77020000082", "Учитель")
    h = await login(client, hr.phone)
    assert (await client.post(f"/api/staff/{admin.id}/password", headers=h, json={"password": "Another-pass-123"})).status_code == 403
    assert (await client.patch(f"/api/staff/{admin.id}", headers=h, json={"position": "x"})).status_code == 403
    assert (await client.patch(f"/api/staff/{hr.id}", headers=h, json={"salary": 999999})).status_code == 403
    # A teacher's rights are not a subset of HR's either → no reset
    assert (await client.post(f"/api/staff/{t.id}/password", headers=h, json={"password": "Another-pass-123"})).status_code == 403


async def test_system_roles_and_portal_users_locked(db, client, owner_h):
    mgr = await _role_user(db, client, owner_h, "rolemgr", [("roles", "view", "network"), ("roles", "manage", "network"),
                                                           ("students", "view", "network")], "+77020000083")
    h = await login(client, mgr.phone)
    parent_role = await db.scalar(select(Role).where(Role.code == "parent"))
    r = await client.put(f"/api/roles/{parent_role.id}", headers=h, json={
        "name": "Родитель", "permissions": [{"module": "students", "action": "view", "scope": "network"}]})
    assert r.status_code == 403
    # Even if the owner did it, a parent account never reaches staff endpoints
    await client.put(f"/api/roles/{parent_role.id}", headers=owner_h, json={
        "name": "Родитель", "permissions": [{"module": "students", "action": "view", "scope": "network"},
                                            {"module": "chats", "action": "use", "scope": "own"}]})
    _, _, _, (a, _) = await _world(db, client, owner_h)
    pa = await _portal_login(db, client, a["guardians"][0]["user_id"])
    assert (await client.get("/api/students", headers=pa)).status_code == 403


async def test_final_test_score_capped_and_not_self_paid(db, client, owner_h):
    _, teacher, g, (a, _) = await _world(db, client, owner_h)
    t = (await client.post("/api/tests", headers=owner_h, json={"kind": "final", "title": "Final ELE", "level_id": g["level_id"],
                                                                 "max_score": 150, "pass_score": 90, "is_published": True})).json()
    th = await login(client, teacher.phone)
    r = await client.post(f"/api/tests/{t['id']}/results", headers=th, json={"student_id": a["id"], "manual_score": 99999})
    assert r.status_code in (400, 422)
    r = await client.post(f"/api/tests/{t['id']}/results", headers=th, json={"student_id": a["id"], "manual_score": 140})
    assert r.status_code == 201 and r.json()["status"] == "needs_review"
    assert not await db.scalar(select(Accrual).where(Accrual.kind == "final_test"))
    r = await client.put(f"/api/attempts/{r.json()['id']}/review", headers=owner_h, json={"manual_score": 140})
    assert r.json()["status"] == "done"
    assert await db.scalar(select(Accrual).where(Accrual.kind == "final_test", Accrual.user_id == teacher.id))


async def test_no_cheaper_level_without_discount_right(db, client, owner_h):
    y = await branch_id(db, YANGI)
    om = await make_staff(db, "office_manager", [YANGI], "+77020000084")
    r = await client.post("/api/students", headers=owner_h, json={"full_name": "Студент INT", "branch_id": y,
                                                                   "level_id": await level_id(db, "INT")})
    oh = await login(client, om.phone)
    r = await client.post("/api/payments", headers=oh, json={"student_id": r.json()["id"], "lessons": 8, "method": "cash",
                                                             "level_id": await level_id(db, "BEG")})
    assert r.status_code == 403


async def test_homework_coins_only_for_group_members(db, client, owner_h):
    _, teacher, g, _ = await _world(db, client, owner_h)
    other = await client.post("/api/students", headers=owner_h, json={"full_name": "Чужой ученик", "branch_id": await branch_id(db, SEVER),
                                                                       "level_id": await level_id(db, "ELE")})
    th = await login(client, teacher.phone)
    hw = (await client.post(f"/api/groups/{g['id']}/homework", headers=th, json={"title": "WB p.5"})).json()
    r = await client.put(f"/api/homework/{hw['id']}/submissions/{other.json()['id']}", headers=th, json={"grade": 5})
    assert r.status_code == 404
    assert not await db.scalar(select(CoinEntry).where(CoinEntry.student_id == other.json()["id"]))


async def test_shop_item_and_leaderboard_scoped(db, client, owner_h):
    y = await branch_id(db, YANGI)
    item = (await client.post("/api/shop/items", headers=owner_h, json={"name": "Кружка", "price_coins": 300, "stock": 5,
                                                                      "branch_id": y})).json()
    admin_s = await make_staff(db, "branch_admin", [SEVER], "+77020000085")
    ah = await login(client, admin_s.phone)
    r = await client.patch(f"/api/shop/items/{item['id']}", headers=ah, json={"name": "Кружка", "price_coins": 1, "stock": 9999})
    assert r.status_code == 403
    sales = await make_staff(db, "sales", [YANGI], "+77020000086")
    assert (await client.get("/api/coins/top", headers=await login(client, sales.phone))).status_code == 403


async def test_unknown_phone_locks_like_real_one(client, db):
    for _ in range(5):
        r = await client.post("/api/auth/login", json={"phone": "+77019999999", "password": "wrong-pass-123"})
        assert r.status_code == 401
    r = await client.post("/api/auth/login", json={"phone": "+77019999999", "password": "wrong-pass-123"})
    assert r.status_code in (423, 429)


def test_production_refuses_dev_secrets(monkeypatch):
    from app.core import config

    monkeypatch.setenv("OE_ENV", "production")
    monkeypatch.setenv("OE_JWT_SECRET", "x" * 40)
    config.get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="OE_META_APP_SECRET"):
            config.get_settings()
    finally:
        monkeypatch.setenv("OE_ENV", "test")
        config.get_settings.cache_clear()
