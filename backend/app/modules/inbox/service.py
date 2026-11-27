"""Unified Instagram + WhatsApp inbox. Every new person who writes becomes a lead (DECISIONS.md №5)."""

import logging
import re
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import normalize_phone
from app.models import Branch, Conversation, ExternalContact, ExternalMessage, Lead, LeadEvent, LeadStage
from app.models.crm import LeadSource
from app.modules.crm.service import create_lead, crm_people, find_by_phone, find_client_by_phone
from app.services import meta
from app.services.clock import now
from app.services.messaging import notify_user
from app.services.realtime import publish
from app.services.values import setting

log = logging.getLogger("inbox")
WINDOW = timedelta(hours=24)
IG_HUMAN_WINDOW = timedelta(days=7)
NO_NAME = "Без имени"


def in_window(conv: Conversation) -> bool:
    """Free-form reply allowed: WhatsApp 24 h; Instagram 7 days when a person answers (HUMAN_AGENT tag)."""
    window = IG_HUMAN_WINDOW if conv.channel == "instagram" else WINDOW
    return conv.last_inbound_at is not None and now() - conv.last_inbound_at < window


async def line_branch(db: AsyncSession, line: int | None) -> int | None:
    """A WhatsApp line is the branch whose number it is; 0 or nothing is the first number, which has no branch."""
    if not line:
        return None
    b = await db.get(Branch, line)
    return b.id if b and b.archived_at is None else None


async def wa_phone_ids(db: AsyncSession) -> dict[int, str]:
    """Official WhatsApp numbers of the branches: {branch id: Meta phone number id}. The first number is in the env."""
    raw = await setting(db, "wa_numbers")
    out: dict[int, str] = {}
    for k, v in raw.items() if isinstance(raw, dict) else []:
        if str(k).isdigit() and int(k) > 0 and isinstance(v, str) and v.isdigit() and len(v) <= 32:
            out[int(k)] = v
    return out


def _conv_of(contact_id: int, line: int | None):
    """The chat of this person with this number of the school (a person may write to both branches)."""
    q = select(Conversation).where(Conversation.contact_id == contact_id)
    return q.where(Conversation.wa_line == line if line else Conversation.wa_line.is_(None)).order_by(Conversation.id.desc())


async def _contact(db: AsyncSession, channel: str, external_id: str, name: str | None, username: str | None,
                   phone: str | None) -> tuple[ExternalContact, bool]:
    c = await db.scalar(select(ExternalContact).where(ExternalContact.channel == channel, ExternalContact.external_id == external_id))
    if c:
        if name and not c.display_name:
            c.display_name = name
        if username and not c.username:
            c.username = username
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
        if existing.branch_id == branch_id and existing.phone == contact.phone and existing.student_id is None:
            # A refusal older than 30 days is closed for good; the person writing again starts a fresh card.
            existing.archived_at = now()
            db.add(LeadEvent(lead_id=existing.id, at=now(), kind="note", text="Архив: клиент написал снова, создан новый лид",
                             actor_id=None, meta={}))
            await db.flush()
    source = LeadSource.WHATSAPP if contact.channel == "whatsapp" else LeadSource.INSTAGRAM
    name = contact.display_name or (f"@{contact.username}" if contact.username else NO_NAME)
    lead = await create_lead(db, full_name=name, phone=contact.phone, branch_id=branch_id, source=source, owner_id=None,
                             notify=False)
    contact.lead_id = lead.id
    return lead


async def receive(db: AsyncSession, *, channel: str, external_id: str, message_id: str, text: str | None,
                  kind: str = "text", media_url: str | None = None, name: str | None = None, username: str | None = None,
                  phone: str | None = None, at: datetime | None = None, make_lead: bool = True,
                  wa_line: int | None = None) -> ExternalMessage | None:
    """Store one inbound message idempotently (Meta retries webhooks)."""
    if await db.scalar(select(ExternalMessage.id).where(ExternalMessage.external_message_id == message_id)):
        return None
    phone = normalize_phone(phone) if phone else None
    contact, _ = await _contact(db, channel, external_id, name, username, phone)
    wa_line = wa_line or None
    conv = await db.scalar(_conv_of(contact.id, wa_line))
    # A new person has no branch yet: staff pick it when they get in touch or book the trial (owner, 18.11.2026).
    # Unless he wrote to a branch's own WhatsApp number: then the branch is known at once (owner, 27.11.2026).
    own = await line_branch(db, wa_line)
    branch_id = conv.branch_id if conv else own
    if make_lead:
        lead = await _link_lead(db, contact, branch_id)
    else:  # a comment without a request: it is shown in «Входящие», a lead is not made for it
        lead = await db.get(Lead, contact.lead_id) if contact.lead_id else None
    if lead:
        if own and lead.branch_id is None:
            from app.modules.crm.service import set_branch

            await set_branch(db, lead, own, None)
        if not own:
            branch_id = lead.branch_id
        if lead.full_name == NO_NAME and (contact.display_name or contact.username):
            lead.full_name = contact.display_name or f"@{contact.username}"  # the name became known later
    if conv is None:
        conv = Conversation(contact_id=contact.id, channel=channel, branch_id=branch_id, wa_line=wa_line,
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
    title = f"{contact.display_name or (lead.full_name if lead else None) or 'Новое сообщение'}: {conv.last_preview[:80]}"
    if conv.assignee_id:
        # The manager who answers this client gets every next message on the screen at once (owner, 21.11.2026).
        from app.services.crm import alert

        await alert(db, conv.assignee_id, "inbox", title, link=f"/inbox/{conv.id}")
    elif conv.unread == 1:
        for uid in await crm_people(db, branch_id, "inbox"):
            await notify_user(db, uid, "inbox", title, link=f"/inbox/{conv.id}", meta_={"channel": channel})
    for b in [branch_id] if branch_id else await db.scalars(select(Branch.id).where(Branch.archived_at.is_(None))):
        await publish(f"inbox:branch:{b}", {"type": "inbox.message", "conversation_id": conv.id, "message_id": msg.id})
    return msg


def _ts(v) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(v) / (1000 if int(v) > 10**11 else 1), tz=UTC)
    except (TypeError, ValueError):
        return None


async def _one(db: AsyncSession, what: str, coro) -> bool:
    """Run one webhook item in its own savepoint: a broken item is logged and skipped, the rest are stored (QA C-9)."""
    try:
        async with db.begin_nested():
            return bool(await coro)
    except Exception:  # noqa: BLE001 — Meta sends what it sends; one odd item must not lose the batch
        log.warning("Meta webhook: skipped %s", what, exc_info=True)
        return False


def _dicts(value) -> list[dict]:
    return [x for x in value if isinstance(x, dict)] if isinstance(value, list) else []


async def _wa_message(db: AsyncSession, m: dict, names: dict, line: int | None = None) -> bool:
    kind = m.get("type", "text")
    body = m.get(kind) if isinstance(m.get(kind), dict) else {}
    text = body.get("body") if kind == "text" else body.get("caption")
    mapped = {"image": "image", "audio": "audio", "voice": "audio", "document": "file", "video": "file"}.get(kind, "text")
    wa_id = m.get("from")
    if not isinstance(wa_id, str) or not isinstance(m.get("id"), str):
        raise ValueError("message without sender or id")
    return await receive(db, channel="whatsapp", external_id=wa_id, message_id=m["id"],
                         text=str(text)[:4000] if text is not None else None, kind=mapped,
                         media_url=body.get("id") if kind != "text" else None, name=names.get(wa_id), phone=wa_id,
                         at=_ts(m.get("timestamp")), wa_line=line) is not None


async def _wa_echo(db: AsyncSession, m: dict, line: int | None = None) -> bool:
    """The number also lives in the WhatsApp Business app on the school's phone: an answer typed there is shown in
    the chat on the site as an outgoing message. It makes no lead and no unread mark."""
    to, mid = m.get("to"), m.get("id")
    if not isinstance(to, str) or not isinstance(mid, str):
        raise ValueError("echo without recipient or id")
    if await db.scalar(select(ExternalMessage.id).where(ExternalMessage.external_message_id == mid)):
        return False
    kind = m.get("type", "text")
    body = m.get(kind) if isinstance(m.get(kind), dict) else {}
    text = body.get("body") if kind == "text" else body.get("caption")
    mapped = {"image": "image", "audio": "audio", "voice": "audio", "document": "file", "video": "file"}.get(kind, "text")
    contact, _ = await _contact(db, "whatsapp", to, None, None, normalize_phone(to))
    conv = await db.scalar(_conv_of(contact.id, line))
    if conv is None:
        lead = await db.get(Lead, contact.lead_id) if contact.lead_id else None
        conv = Conversation(contact_id=contact.id, channel="whatsapp", wa_line=line or None,
                            branch_id=await line_branch(db, line) or (lead.branch_id if lead else None),
                            assignee_id=lead.assignee_id if lead else None)
        db.add(conv)
        await db.flush()
    t = _ts(m.get("timestamp")) or now()
    preview = (str(text)[:4000] if text else {"image": "Фото", "audio": "Голосовое", "file": "Файл"}.get(mapped, "Сообщение"))
    db.add(ExternalMessage(conversation_id=conv.id, at=t, direction="out", external_message_id=mid, kind=mapped,
                           text=str(text)[:4000] if text else None, media_url=body.get("id") if kind != "text" else None,
                           status="sent"))
    if conv.last_message_at is None or t >= conv.last_message_at:
        conv.last_message_at, conv.last_preview = t, "С телефона: " + preview[:240]
    conv.unread = 0  # answered from the phone
    await db.flush()
    for b in [conv.branch_id] if conv.branch_id else await db.scalars(select(Branch.id).where(Branch.archived_at.is_(None))):
        await publish(f"inbox:branch:{b}", {"type": "inbox.message", "conversation_id": conv.id})
    return True


async def _bridge_out(db: AsyncSession, chat: str, mid: str, kind: str, text: str | None, at: datetime | None,
                      line: int | None = None) -> bool:
    """An answer typed on the school's phone. Shown only in a chat the site already has: the same number also holds
    personal chats, and what the owner writes to people the school does not know stays on the phone."""
    contact = await db.scalar(select(ExternalContact).where(ExternalContact.channel == "whatsapp", ExternalContact.external_id == chat))
    conv = contact and await db.scalar(_conv_of(contact.id, line))
    if not conv or await db.scalar(select(ExternalMessage.id).where(ExternalMessage.external_message_id == mid)):
        return False
    t = at or now()
    preview = text or {"image": "Фото", "audio": "Голосовое", "file": "Файл"}.get(kind, "Сообщение")
    db.add(ExternalMessage(conversation_id=conv.id, at=t, direction="out", external_message_id=mid, kind=kind, text=text, status="sent"))
    if conv.last_message_at is None or t >= conv.last_message_at:
        conv.last_message_at, conv.last_preview = t, "С телефона: " + preview[:240]
    conv.unread = 0  # answered from the phone
    await db.flush()
    for b in [conv.branch_id] if conv.branch_id else await db.scalars(select(Branch.id).where(Branch.archived_at.is_(None))):
        await publish(f"inbox:branch:{b}", {"type": "inbox.message", "conversation_id": conv.id})
    return True


BRIDGE_CHAT = re.compile(r"^(lid:)?\d{5,20}$")


async def handle_bridge_events(db: AsyncSession, events: list) -> int:
    """Messages from the WhatsApp linked by QR (wa/bridge.mjs). The message id is prefixed: it is a short id of the
    WhatsApp protocol, not Meta's «wamid…»."""
    stored = 0
    for ev in _dicts(events)[:200]:
        chat, mid, kind = ev.get("chat"), ev.get("id"), ev.get("kind")
        if not isinstance(chat, str) or not BRIDGE_CHAT.match(chat) or not isinstance(mid, str) or not 0 < len(mid) <= 200:
            continue
        kind = kind if kind in ("text", "image", "audio", "file") else "text"
        text = str(ev["text"])[:4000] if isinstance(ev.get("text"), str) and ev["text"] else None
        phone = ev.get("phone") if isinstance(ev.get("phone"), str) and ev["phone"].isdigit() else None
        name = str(ev["name"])[:120] if isinstance(ev.get("name"), str) and ev["name"].strip() else None
        line = ev.get("line") if type(ev.get("line")) is int and 0 < ev["line"] <= 1_000_000 else None
        if ev.get("type") == "in":
            coro = receive(db, channel="whatsapp", external_id=chat, message_id="wab:" + mid, text=text, kind=kind, name=name,
                           phone=phone, at=_ts(ev.get("ts")), wa_line=line)
        elif ev.get("type") == "out":
            coro = _bridge_out(db, chat, "wab:" + mid, kind, text, _ts(ev.get("ts")), line)
        else:
            continue
        stored += await _one(db, "WhatsApp link message", coro)
    return stored


async def _wa_status(db: AsyncSession, st: dict) -> bool:
    msg = await db.scalar(select(ExternalMessage).where(ExternalMessage.external_message_id == st.get("id")))
    if msg and st.get("status") in ("sent", "delivered", "read", "failed"):
        msg.status = st["status"]
        if st["status"] == "failed":
            msg.error = str((_dicts(st.get("errors")) or [{}])[0].get("title", ""))[:250]
    return False


async def _ig_event(db: AsyncSession, ev: dict) -> bool:
    m = ev.get("message") if isinstance(ev.get("message"), dict) else {}
    if not m or m.get("is_echo"):
        return False
    att = (_dicts(m.get("attachments")) or [{}])[0]
    kind = {"image": "image", "audio": "audio", "file": "file", "video": "file"}.get(att.get("type"), "text")
    if (m.get("reply_to") or {}).get("story"):
        kind = "story_reply"
        text = str(m.get("text") or "")
        if "+" not in text and not any(ch.isalnum() for ch in text):
            return False  # a reaction to a story (an emoji, a heart): not a message from a client, not stored
    sender = (ev.get("sender") or {}).get("id")
    if not isinstance(sender, str) or not isinstance(m.get("mid"), str):
        raise ValueError("event without sender or id")
    name = username = None
    known = await db.scalar(select(ExternalContact).where(ExternalContact.channel == "instagram",
                                                          ExternalContact.external_id == sender))
    if known is None or not (known.display_name and known.username):
        name, username = await meta.ig_profile(sender)
    return await receive(db, channel="instagram", external_id=sender, message_id=m["mid"], text=m.get("text"), kind=kind,
                         media_url=(att.get("payload") or {}).get("url"), at=_ts(ev.get("timestamp")),
                         name=name or (f"@{username}" if username else None), username=username) is not None


COMMENT_PREFIX = "igc_"


def comment_kind(text: str, words) -> str:
    """Owner, 20.11.2026: not every comment is a client. "noise" — nothing but emoji, stickers or @friends;
    "lead" — it has one of the request words from the settings («цена», «сколько», «+»…); "plain" — any other text.
    An empty word list means every comment with text makes a lead, as before."""
    body = re.sub(r"@[\w.]+", " ", text).lower()
    if "+" not in body and not any(ch.isalnum() for ch in body):
        return "noise"
    keys = [w.strip().lower() for w in re.split(r"[,;\n]", words if isinstance(words, str) else "") if w.strip()]
    return "lead" if not keys or any(k in body for k in keys) else "plain"


async def _ig_comment(db: AsyncSession, value: dict, own_id) -> bool:
    """A comment under the school's post or Reels: its author becomes a contact (and a lead) like someone who wrote
    to Direct. The school's own comments and answers are skipped."""
    author = value.get("from") if isinstance(value.get("from"), dict) else {}
    cid, sender = value.get("id"), author.get("id")
    if not isinstance(cid, str) or not isinstance(sender, str):
        raise ValueError("comment without id or author")
    if sender == str(own_id) or not str(value.get("text") or "").strip():
        return False
    what = comment_kind(str(value["text"]), await setting(db, "ig_comment_lead_words"))
    if what == "noise":
        return False  # only emoji, stickers or tagged friends: not a request, not stored
    username = author.get("username") if isinstance(author.get("username"), str) else None
    return await receive(db, channel="instagram", external_id=sender, message_id=COMMENT_PREFIX + cid,
                         text=f"Комментарий: {str(value['text'])[:3900]}", username=username,
                         name=f"@{username}" if username else None, make_lead=what == "lead") is not None


async def comment_to_answer(db: AsyncSession, conv: Conversation) -> str | None:
    """Id of the comment the next answer goes to as a private reply: the last thing in the chat is this person's
    comment and nobody has answered it yet. Otherwise the chat goes on in Direct."""
    last = await db.scalar(select(ExternalMessage).where(ExternalMessage.conversation_id == conv.id)
                           .order_by(ExternalMessage.at.desc(), ExternalMessage.id.desc()).limit(1))
    if last and last.direction == "in" and (last.external_message_id or "").startswith(COMMENT_PREFIX):
        return last.external_message_id.removeprefix(COMMENT_PREFIX)
    return None


async def handle_meta_payload(db: AsyncSession, payload) -> int:
    """Parse a Meta webhook: WhatsApp Cloud API (`whatsapp_business_account`) or Instagram (`instagram`).
    Each entry, message and status is handled on its own; whatever is malformed is logged and skipped."""
    if not isinstance(payload, dict):
        log.warning("Meta webhook: payload is %s, not an object — ignored", type(payload).__name__)
        return 0
    n = 0
    obj = payload.get("object")
    by_phone = {v: k for k, v in (await wa_phone_ids(db)).items()} if obj == "whatsapp_business_account" else {}
    for entry in payload.get("entry") if isinstance(payload.get("entry"), list) else []:
        if not isinstance(entry, dict):
            log.warning("Meta webhook: skipped entry %r", entry)
            continue
        if obj == "whatsapp_business_account":
            for change in _dicts(entry.get("changes")):
                value = change.get("value") if isinstance(change.get("value"), dict) else {}
                names = {c.get("wa_id"): (c.get("profile") or {}).get("name") for c in _dicts(value.get("contacts"))}
                # which of the school's numbers got it: a branch's own number, or the first one
                md = value.get("metadata") if isinstance(value.get("metadata"), dict) else {}
                line = by_phone.get(md.get("phone_number_id"))
                for m in _dicts(value.get("messages")):
                    n += await _one(db, f"message {m.get('id')}", _wa_message(db, m, names, line))
                for st in _dicts(value.get("statuses")):
                    await _one(db, f"status {st.get('id')}", _wa_status(db, st))
                if change.get("field") == "smb_message_echoes":
                    for m in _dicts(value.get("message_echoes")):
                        await _one(db, f"echo {m.get('id')}", _wa_echo(db, m, line))
        elif obj == "instagram":
            for ev in _dicts(entry.get("messaging")):
                n += await _one(db, f"event {ev.get('timestamp')}", _ig_event(db, ev))
            for change in _dicts(entry.get("changes")):
                if change.get("field") in ("comments", "live_comments") and isinstance(change.get("value"), dict):
                    n += await _one(db, f"comment {change['value'].get('id')}", _ig_comment(db, change["value"], entry.get("id")))
    return n
