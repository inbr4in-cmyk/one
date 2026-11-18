from datetime import timedelta

from sqlalchemy import select

from app.models import Lead, LeadStage
from app.services.clock import local, today
from tests.conftest import branch_id, login, make_staff

YANGI = "Янги шахар"


async def test_lead_history_names_every_step(client, db, owner_h, owner):
    bid = await branch_id(db, YANGI)
    lead = (await client.post("/api/crm/leads", headers=owner_h, json={"full_name": "Алия", "branch_id": bid})).json()
    await client.post(f"/api/crm/leads/{lead['id']}/events", headers=owner_h, json={"kind": "call", "text": "Позвонил, думает"})
    await client.patch(f"/api/crm/leads/{lead['id']}", headers=owner_h, json={"phone": "+77015550101"})
    card = (await client.get(f"/api/crm/leads/{lead['id']}", headers=owner_h)).json()
    texts = [e["text"] for e in card["events"]]
    assert "Изменено: телефон" in texts and "Позвонил, думает" in texts
    assert all(e["actor_name"] == owner.full_name for e in card["events"])
    assert card["lead"]["assignee_name"] == owner.full_name
    other = await make_staff(db, "sales", [YANGI], "+77080000779", "Новый Ответственный")
    await db.commit()
    r = await client.patch(f"/api/crm/leads/{lead['id']}", headers=owner_h, json={"assignee_id": other.id})
    assert r.json()["assignee_name"] == "Новый Ответственный"
    card = (await client.get(f"/api/crm/leads/{lead['id']}", headers=owner_h)).json()
    assert card["events"][0]["text"] == "Ответственный: Новый Ответственный" and card["events"][0]["actor_name"] == owner.full_name
    assert (await client.patch(f"/api/crm/leads/{lead['id']}", headers=owner_h, json={"assignee_id": 999999})).status_code == 400


async def test_lead_can_be_dated_back_a_month_at_most(client, db, owner_h):
    bid = await branch_id(db, YANGI)
    day = today() - timedelta(days=5)
    r = await client.post("/api/crm/leads", headers=owner_h, json={"full_name": "Вчерашний", "branch_id": bid,
                                                                  "contacted_on": day.isoformat()})
    assert r.status_code == 201
    lead = await db.get(Lead, r.json()["id"])
    await db.refresh(lead)
    assert local(lead.created_at).date() == day
    card = (await client.get(f"/api/crm/leads/{lead.id}", headers=owner_h)).json()
    assert f"дата обращения {day:%d.%m.%Y}" in card["events"][-1]["text"]
    assert local(__import__("datetime").datetime.fromisoformat(card["events"][-1]["at"])).date() == today()  # entered today
    for bad in (today() - timedelta(days=40), today() + timedelta(days=1)):
        r = await client.post("/api/crm/leads", headers=owner_h, json={"full_name": "Нельзя", "branch_id": bid,
                                                                      "contacted_on": bad.isoformat()})
        assert r.status_code == 400


async def test_admin_closes_funnel_stages_per_person(client, db, owner_h):
    bid = await branch_id(db, YANGI)
    sales = await make_staff(db, "sales", [YANGI], "+77080000777", "Менеджер Сауле")
    await db.commit()
    h = await login(client, sales.phone)
    lead = (await client.post("/api/crm/leads", headers=h, json={"full_name": "Тимур", "branch_id": bid})).json()
    new = await db.scalar(select(LeadStage).where(LeadStage.code == "new"))
    contacted = await db.scalar(select(LeadStage).where(LeadStage.code == "contacted"))
    table = (await client.get("/api/crm/stage-access", headers=owner_h)).json()
    assert any(u["id"] == sales.id and u["can_edit"] for u in table["users"]) and table["cells"] == {}
    assert (await client.get("/api/crm/stage-access", headers=h)).status_code == 403  # only who manages roles

    # view only: the card opens, nothing can be changed
    r = await client.put("/api/crm/stage-access", headers=owner_h, json={"user_id": sales.id, "stage_id": new.id, "level": "view"})
    assert r.status_code == 204
    card = (await client.get(f"/api/crm/leads/{lead['id']}", headers=h)).json()
    assert card["lead"]["can_edit"] is False
    assert (await client.patch(f"/api/crm/leads/{lead['id']}", headers=h, json={"notes": "x"})).status_code == 403
    assert (await client.post(f"/api/crm/leads/{lead['id']}/stage", headers=h, json={"stage_id": contacted.id})).status_code == 403

    # hidden: no column, no card
    await client.put("/api/crm/stage-access", headers=owner_h, json={"user_id": sales.id, "stage_id": new.id, "level": "none"})
    cols = (await client.get("/api/crm/board", headers=h)).json()["columns"]
    assert new.id not in {c["stage"]["id"] for c in cols}
    assert (await client.get(f"/api/crm/leads/{lead['id']}", headers=h)).status_code == 404
    assert new.id in {c["stage"]["id"] for c in (await client.get("/api/crm/board", headers=owner_h)).json()["columns"]}

    # only own: other people's leads on that stage are not shown, own ones stay editable
    other = (await client.post("/api/crm/leads", headers=owner_h, json={"full_name": "Чужой", "branch_id": bid})).json()
    await client.put("/api/crm/stage-access", headers=owner_h, json={"user_id": sales.id, "stage_id": new.id, "level": "own"})
    col = next(c for c in (await client.get("/api/crm/board", headers=h)).json()["columns"] if c["stage"]["id"] == new.id)
    assert {x["id"] for x in col["leads"]} == {lead["id"]} and col["total"] == 1
    assert (await client.get(f"/api/crm/leads/{other['id']}", headers=h)).status_code == 404
    assert (await client.patch(f"/api/crm/leads/{lead['id']}", headers=h, json={"notes": "моё"})).status_code == 200

    # back to what the role gives
    await client.put("/api/crm/stage-access", headers=owner_h, json={"user_id": sales.id, "stage_id": new.id, "level": "edit"})
    assert (await client.get("/api/crm/stage-access", headers=owner_h)).json()["cells"] == {}
    assert (await client.patch(f"/api/crm/leads/{lead['id']}", headers=h, json={"notes": "x"})).status_code == 200


async def test_instagram_lead_has_no_branch_until_staff_pick_it(client, db, owner_h, monkeypatch):
    from app.services import meta
    from tests.test_crm_inbox import ig_payload, signed

    async def nobody(user_id):
        return None, None

    monkeypatch.setattr(meta, "ig_profile", nobody)
    bid = await branch_id(db, YANGI)
    sales = await make_staff(db, "sales", [YANGI], "+77080000778", "Менеджер филиала")
    await db.commit()
    h = await login(client, sales.phone)
    body, hd = signed(ig_payload("17841400000000091", "ig.b1", "Здравствуйте"))
    await client.post("/api/webhooks/meta", content=body, headers=hd)
    conv = (await client.get("/api/inbox/conversations", headers=h)).json()[0]  # a branch manager sees it too
    assert conv["branch_id"] is None
    lead_id = conv["lead"]["id"]
    card = (await client.get(f"/api/crm/leads/{lead_id}", headers=h)).json()["lead"]
    assert card["branch_id"] is None
    cols = (await client.get(f"/api/crm/board?branch_id={bid}", headers=h)).json()["columns"]
    assert any(x["id"] == lead_id for c in cols for x in c["leads"])
    assert (await client.post(f"/api/crm/leads/{lead_id}/convert", headers=owner_h, json={})).status_code == 400
    r = await client.patch(f"/api/crm/leads/{lead_id}", headers=h, json={"branch_id": bid})
    assert r.status_code == 200 and r.json()["branch_id"] == bid
    assert (await client.get(f"/api/inbox/conversations/{conv['id']}", headers=h)).json()["branch_id"] == bid
    events = (await client.get(f"/api/crm/leads/{lead_id}", headers=h)).json()["events"]
    assert any(e["text"] == f"Филиал: {YANGI}" and e["actor_name"] == "Менеджер филиала" for e in events)
