"""«Реклама»: what the Facebook / Instagram ads cost and what they brought, next to the CRM numbers (owner, 28.11.2026)."""
from datetime import date, timedelta

from fastapi import APIRouter
from sqlalchemy import func, select

from app.core.audit import write_audit
from app.core.deps import DB, Actor, require
from app.core.errors import bad_request
from app.models import AdInsight, Lead, LeadStage
from app.services import ads, meta
from app.services import crm as crm_svc
from app.services.clock import local_range, today

router = APIRouter(tags=["ads"])

# Leads that come from the ads: the school advertises in Instagram and to WhatsApp.
AD_SOURCES = ("instagram", "whatsapp")


@router.get("/ads/report")
async def report(db: DB, actor: Actor = require("finance", "view"), date_from: date | None = None, date_to: date | None = None) -> dict:
    d2 = date_to or today()
    d1 = date_from or d2.replace(day=1)
    if d1 > d2:
        d1, d2 = d2, d1
    d1 = max(d1, d2 - timedelta(days=366))
    rows = list(await db.scalars(select(AdInsight).where(AdInsight.day >= d1, AdInsight.day <= d2).order_by(AdInsight.day)))

    def total(items) -> dict:
        spend = float(sum(x.spend for x in items))
        imp, clicks = sum(x.impressions for x in items), sum(x.clicks for x in items)
        return {"spend": round(spend, 2), "impressions": imp, "reach": sum(x.reach for x in items), "clicks": clicks,
                "link_clicks": sum(x.link_clicks for x in items), "results": sum(x.results for x in items),
                "ctr": round(100 * clicks / imp, 2) if imp else 0.0, "cpc": round(spend / clicks, 2) if clicks else None}

    by_day: dict = {}
    by_campaign: dict = {}
    for x in rows:
        by_day.setdefault(x.day, []).append(x)
        by_campaign.setdefault(x.campaign_id, []).append(x)
    start, end = local_range(d1, d2)
    won = select(LeadStage.id).where(LeadStage.is_won.is_(True))
    scope = [Lead.created_at >= start, Lead.created_at < end, Lead.source.in_(AD_SOURCES), Lead.archived_at.is_(None), crm_svc.not_return()]
    leads = await db.scalar(select(func.count()).select_from(Lead).where(*scope)) or 0
    paid = await db.scalar(select(func.count()).select_from(Lead).where(*scope, Lead.stage_id.in_(won))) or 0
    t = total(rows)
    return {"configured": meta.ads_ready(), "period": [d1, d2], "currency": next((x.currency for x in reversed(rows) if x.currency), ""),
            "synced_at": max((x.synced_at for x in rows), default=None), "total": t,
            "crm": {"leads": leads, "paid": paid, "cost_per_lead": round(t["spend"] / leads, 2) if leads else None,
                    "cost_per_paid": round(t["spend"] / paid, 2) if paid else None},
            "days": [{"day": d, **total(v)} for d, v in by_day.items()],
            "campaigns": sorted(({"id": k, "name": v[-1].campaign_name, **total(v)} for k, v in by_campaign.items()),
                                key=lambda r: -r["spend"])}


@router.post("/ads/sync")
async def sync_now(db: DB, actor: Actor = require("finance", "view"), days: int = 30) -> dict:
    """«Обновить»: reads the statistics from Meta now (the nightly job does the same for the last week)."""
    if not meta.ads_ready():
        raise bad_request("Реклама не подключена: ключ вводится на сервере")
    try:
        out = await ads.sync(db, days=min(max(days, 1), 90))
    except RuntimeError as e:
        raise bad_request(f"Meta отказала: {e}") from None
    await write_audit(db, actor_id=actor.id, action="ads.sync", entity="ads", entity_id=0, ip=actor.ip, after=out)
    await db.commit()
    return out
