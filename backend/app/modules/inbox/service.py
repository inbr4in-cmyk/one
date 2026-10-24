"""Unified Instagram + WhatsApp inbox. Every new person who writes becomes a lead (DECISIONS.md №5)."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import normalize_phone
from app.models import Conversation, ExternalContact, ExternalMessage, Lead, LeadEvent, LeadStage
from app.models.crm import LeadSource
from app.modules.crm.service import create_lead, crm_people, default_branch_id, find_by_phone, find_client_by_phone
from app.services.clock import now
from app.services.messaging import notify_user
from app.services.realtime import publish

WINDOW = timedelta(hours=24)


def in_window(conv: Conversation) -> bool:
    return conv.last_inbound_at is not None and now() - conv.last_inbound_at < WINDOW


async def _contact(db: AsyncSession, channel: str, external_id: str, name: str | None, username: str | None,
                   phone: str | None) -> tuple[ExternalContact, bool]:
    c = await db.scalar(select(ExternalContact).where(ExternalContact.channel == channel, ExternalContact.external_id == external_id))
    if c:
        if name and not c.display_name:
            c.display_name = name
        return c, False
    c = ExternalContact(channel=channel, external_id=external_id, display_name=name, username=username, phone=phone)
    db.add(c)
    await db.flush()
    return c, True


async def _link_lead(db: AsyncSession, contact: ExternalContact, branch_id: int) -> Lead | None:
    """Existing student/parent → no new lead. Open lead with the same phone → reuse. Otherwise create one."""
    if contact.lead_id or contact.student_id:
        return await db.get(Lead, contact.lead_id) if contact.lead_id else None
    client = await find_client_by_phone(db, contact.phone)
    if client:
        contact.student_id = client.id
        return None
    existing = await find_by_phone(db, contact.phone)
    if existing:
        st = await db.get(LeadStage, existing.stage_id)
        stale_lost = st and st.is_lost and existing.stage_changed_at < now() - timedelta(days=30)
        if not stale_lost:
            contact.lead_id = existing.id
            return existing
    source = LeadSource.WHATSAPP if contact.channel == "whatsapp" else LeadSource.INSTAGRAM
    name = contact.display_name or (f"@{contact.username}" if contact.username else "Без имени")
    lead = await create_lead(db, full_name=name, phone=contact.phone, branch_id=branch_id, source=source, owner_id=None,
                             notify=False)
    contact.lead_id = lead.id
    return lead


async def receive(db: AsyncSession, *, channel: str, external_id: str, message_id: str, text: str | None,
                  kind: str = "text", media_url: str | None = None, name: str | None = None, username: str | None = None,
                  phone: str | None = None, at: datetime | None = None) -> ExternalMessage | None:
    """Store one inbound message idempotently (Meta retries webhooks)."""
    if await db.scalar(select(ExternalMessage.id).where(ExternalMessage.external_message_id == message_id)):
        return None
    phone = normalize_phone(phone) if phone else None
    contact, _ = await _contact(db, channel, external_id, name, username, phone)
    conv = await db.scalar(select(Conversation).where(Conversation.contact_id == contact.id).order_by(Conversation.id.desc()))
    branch_id = conv.branch_id if conv and conv.branch_id else await default_branch_id(db)
    lead = await _link_lead(db, contact, branch_id)
    if lead:
        branch_id = lead.branch_id
    if conv is None:
        conv = Conversation(contact_id=contact.id, channel=channel, branch_id=branch_id,
                            assignee_id=lead.assignee_id if lead else None)
        db.add(conv)
        await db.flush()
    t = at or now()
    msg = ExternalMessage(conversation_id=conv.id, at=t, direction="in", external_message_id=message_id, kind=kind,
                          text=text, media_url=media_url, status="received")
    db.add(msg)
    conv.unread += 1
    conv.status = "open"
    conv.last_message_at = conv.last_inbound_at = t
    conv.last_preview = (text or {"image": "Фото", "audio": "Голосовое", "file": "Файл"}.get(kind, "Сообщение"))[:255]
    if lead:
        lead.last_activity_at = t
        db.add(LeadEvent(lead_id=lead.id, at=t, kind="message", text=conv.last_preview, actor_id=None, meta={"channel": channel}))
    await db.flush()
    targets = [conv.assignee_id] if conv.assignee_id else await crm_people(db, branch_id, "inbox")
    for uid in targets:
        if uid and conv.unread == 1:
            await notify_user(db, uid, "inbox", f"{contact.display_name or 'Новое сообщение'}: {conv.last_preview[:80]}",
                              link=f"/inbox/{conv.id}", meta_={"channel": channel})
    await publish(f"inbox:branch:{branch_id}", {"type": "inbox.message", "conversation_id": conv.id, "message_id": msg.id})
    return msg


def _ts(v) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(v) / (1000 if int(v) > 10**11 else 1), tz=UTC)
    except (TypeError, ValueError):
        return None


async def handle_meta_payload(db: AsyncSession, payload: dict) -> int:
    """Parse a Meta webhook: WhatsApp Cloud API (`whatsapp_business_account`) or Instagram (`instagram`)."""
    n = 0
    obj = payload.get("object")
    for entry in payload.get("entry", []) or []:
        if obj == "whatsapp_business_account":
            for change in entry.get("changes", []) or []:
                value = change.get("value") or {}
                names = {c.get("wa_id"): (c.get("profile") or {}).get("name") for c in value.get("contacts", []) or []}
                for m in value.get("messages", []) or []:
                    kind = m.get("type", "text")
                    body = m.get(kind) if isinstance(m.get(kind), dict) else {}
                    text = body.get("body") if kind == "text" else body.get("caption")
                    mapped = {"image": "image", "audio": "audio", "voice": "audio", "document": "file", "video": "file"}.get(kind, "text")
                    wa_id = m.get("from")
                    if await receive(db, channel="whatsapp", external_id=wa_id, message_id=m.get("id"), text=text, kind=mapped,
                                     media_url=body.get("id") if kind != "text" else None,
                                     name=names.get(wa_id), phone=wa_id, at=_ts(m.get("timestamp"))):
                        n += 1
                for st in value.get("statuses", []) or []:
                    msg = await db.scalar(select(ExternalMessage).where(ExternalMessage.external_message_id == st.get("id")))
                    if msg and st.get("status") in ("sent", "delivered", "read", "failed"):
                        msg.status = st["status"]
                        if st["status"] == "failed":
                            msg.error = str((st.get("errors") or [{}])[0].get("title", ""))[:250]
        elif obj == "instagram":
            for ev in entry.get("messaging", []) or []:
                m = ev.get("message") or {}
                if not m or m.get("is_echo"):
                    continue
                att = (m.get("attachments") or [{}])[0]
                kind = {"image": "image", "audio": "audio", "file": "file", "video": "file"}.get(att.get("type"), "text")
                if m.get("reply_to", {}).get("story"):
                    kind = "story_reply"
                if await receive(db, channel="instagram", external_id=(ev.get("sender") or {}).get("id"), message_id=m.get("mid"),
                                 text=m.get("text"), kind=kind, media_url=(att.get("payload") or {}).get("url"),
                                 at=_ts(ev.get("timestamp"))):
                    n += 1
    return n
