"""Facebook / Instagram ads statistics kept by day and campaign (owner, 28.11.2026). Read only: nothing is ever
changed in the ad account."""
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AdInsight
from app.services import meta
from app.services.clock import now, today


def _int(v) -> int:
    try:
        return max(0, int(float(v)))
    except (TypeError, ValueError):
        return 0


def _money(v) -> Decimal:
    try:
        return max(Decimal(0), Decimal(str(v))).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(0)


async def sync(db: AsyncSession, days: int = 7, since: date | None = None) -> dict:
    """Reads the last `days` days again (Meta corrects recent numbers for a few days) and saves them."""
    if not meta.ads_ready():
        return {"ok": False, "reason": "not configured"}
    until = today()
    since = since or until - timedelta(days=days - 1)
    rows = await meta.ads_insights(since, until)
    have = {(x.day, x.campaign_id): x for x in await db.scalars(select(AdInsight).where(AdInsight.day >= since, AdInsight.day <= until))}
    n = 0
    for r in rows:
        try:
            day = date.fromisoformat(str(r.get("date_start")))
        except ValueError:
            continue
        cid = str(r.get("campaign_id") or "")[:64]
        if not cid:
            continue
        actions = {str(a.get("action_type")): _int(a.get("value")) for a in r.get("actions") or [] if isinstance(a, dict)}
        x = have.get((day, cid))
        if x is None:
            x = AdInsight(day=day, campaign_id=cid)
            db.add(x)
        x.campaign_name = str(r.get("campaign_name") or "")[:255]
        x.currency = str(r.get("account_currency") or "")[:8]
        x.spend, x.impressions, x.reach = _money(r.get("spend")), _int(r.get("impressions")), _int(r.get("reach"))
        x.clicks, x.link_clicks = _int(r.get("clicks")), _int(r.get("inline_link_clicks"))
        x.results = sum(actions.get(k, 0) for k in meta.RESULT_ACTIONS)
        x.synced_at = now()
        n += 1
    await db.flush()
    return {"ok": True, "rows": n, "since": since.isoformat(), "until": until.isoformat()}
