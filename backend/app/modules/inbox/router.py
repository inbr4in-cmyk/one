import json
import logging

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import or_, select, true

from app.core.audit import write_audit
from app.core.config import get_settings
from app.core.deps import DB, Actor, require
from app.core.errors import bad_request, conflict, not_found
from app.core.permissions import NETWORK, OWN
from app.core.ratelimit import client_ip, hit
from app.core.schemas import ORM
from app.core.security import mask_phone
from app.models import Conversation, ExternalContact, ExternalMessage, Lead, LeadStage
from app.modules.inbox.service import handle_meta_payload, in_window
from app.services import meta
from app.services.clock import now
from app.services.messaging import get_template, render

log = logging.getLogger("inbox")
router = APIRouter(tags=["inbox"])


# ---------- Meta webhooks ----------
@router.get("/webhooks/meta")
async def verify(mode: str = Query(alias="hub.mode", default=""), token: str = Query(alias="hub.verify_token", default=""),
                 challenge: str = Query(alias="hub.challenge", default="")) -> Response:
    if mode == "subscribe" and token == get_settings().meta_verify_token:
        return Response(challenge, media_type="text/plain")
    raise HTTPException(403, "Неверный токен")


@router.post("/webhooks/meta")
async def webhook(request: Request, db: DB) -> dict:
    await hit(f"webhook:{client_ip(request)}", 600, 60)
    body = await request.body()
    if len(body) > 1_000_000:
        raise HTTPException(413, "Слишком большой запрос")
    if not meta.verify_signature(body, request.headers.get("x-hub-signature-256")):
        log.warning("Meta webhook with a bad signature from %s", client_ip(request))
        raise HTTPException(401, "Неверная подпись")
    try:
        payload = json.loads(body)
    except ValueError:
        raise HTTPException(400, "Некорректный JSON") from None
    n = await handle_meta_payload(db, payload)
    await db.commit()
    return {"ok": True, "stored": n}


# ---------- conversations ----------
class ConversationOut(BaseModel):
    id: int
    channel: str
    branch_id: int | None
    assignee_id: int | None
    unread: int
    status: str
    last_message_at: str | None
    last_preview: str | None
    in_window: bool
    contact: dict
    lead: dict | None


class MessageOut(ORM):
    id: int
    at: object
    direction: str
    kind: str
    text: str | None
    media_url: str | None
    status: str
    sender_id: int | None


def conv_filter(actor: Actor, action: str = "view"):
    scope = actor.scope("inbox", action)
    if scope == NETWORK:
        return true()
    if scope == OWN:
        return Conversation.assignee_id == actor.id
    return or_(Conversation.branch_id.in_(actor.branch_ids or {-1}), Conversation.branch_id.is_(None))


async def _out(db: DB, actor: Actor, conv: Conversation) -> ConversationOut:
    c = await db.get(ExternalContact, conv.contact_id)
    lead = await db.get(Lead, c.lead_id) if c.lead_id else None
    stage = await db.get(LeadStage, lead.stage_id) if lead else None
    show = actor.can("students", "view_contacts")
    return ConversationOut(
        id=conv.id, channel=conv.channel, branch_id=conv.branch_id, assignee_id=conv.assignee_id, unread=conv.unread,
        status=conv.status, last_message_at=conv.last_message_at.isoformat() if conv.last_message_at else None,
        last_preview=conv.last_preview, in_window=in_window(conv),
        contact={"id": c.id, "name": c.display_name, "username": c.username,
                 "phone": c.phone if show else mask_phone(c.phone), "student_id": c.student_id},
        lead={"id": lead.id, "full_name": lead.full_name, "stage": stage.name if stage else None,
              "stage_code": stage.code if stage else None, "source": lead.source} if lead else None,
    )


async def _get(db: DB, actor: Actor, conv_id: int, action: str = "view") -> Conversation:
    conv = await db.scalar(select(Conversation).where(Conversation.id == conv_id, conv_filter(actor, action)))
    if conv is None:
        raise not_found("Диалог")
    return conv


@router.get("/inbox/conversations", response_model=list[ConversationOut])
async def conversations(db: DB, actor: Actor = require("inbox", "view"), channel: str | None = None,
                        status: str | None = "open", unread: bool = False, mine: bool = False, q: str | None = None,
                        limit: int = 100) -> list[ConversationOut]:
    stmt = select(Conversation).where(conv_filter(actor))
    if channel:
        stmt = stmt.where(Conversation.channel == channel)
    if status:
        stmt = stmt.where(Conversation.status == status)
    if unread:
        stmt = stmt.where(Conversation.unread > 0)
    if mine:
        stmt = stmt.where(Conversation.assignee_id == actor.id)
    if q:
        stmt = stmt.join(ExternalContact, ExternalContact.id == Conversation.contact_id).where(
            or_(ExternalContact.display_name.ilike(f"%{q}%"), ExternalContact.username.ilike(f"%{q}%")))
    rows = await db.scalars(stmt.order_by(Conversation.last_message_at.desc().nulls_last()).limit(min(limit, 200)))
    return [await _out(db, actor, c) for c in rows]


@router.get("/inbox/conversations/{conv_id}", response_model=ConversationOut)
async def conversation(conv_id: int, db: DB, actor: Actor = require("inbox", "view")) -> ConversationOut:
    return await _out(db, actor, await _get(db, actor, conv_id))


@router.get("/inbox/conversations/{conv_id}/messages", response_model=list[MessageOut])
async def messages(conv_id: int, db: DB, actor: Actor = require("inbox", "view"), before_id: int | None = None,
                   limit: int = 50) -> list[MessageOut]:
    conv = await _get(db, actor, conv_id)
    q = select(ExternalMessage).where(ExternalMessage.conversation_id == conv.id)
    if before_id:
        q = q.where(ExternalMessage.id < before_id)
    rows = list(await db.scalars(q.order_by(ExternalMessage.id.desc()).limit(min(limit, 200))))
    if conv.unread and not before_id:
        conv.unread = 0
        await db.commit()
    return [MessageOut.model_validate(m) for m in reversed(rows)]


class SendIn(BaseModel):
    text: str = Field(min_length=1, max_length=4096)


async def _send(db: DB, actor: Actor, conv: Conversation, text: str, kind: str = "text") -> ExternalMessage:
    contact = await db.get(ExternalContact, conv.contact_id)
    if conv.channel == "whatsapp":
        res = await meta.wa_send_text(contact.external_id, text)
    else:
        res = await meta.ig_send_text(contact.external_id, text)
    msg = ExternalMessage(conversation_id=conv.id, at=now(), direction="out", external_message_id=res.external_id, kind=kind,
                          text=text, status="sent" if res.ok else "failed", error=res.error, sender_id=actor.id)
    db.add(msg)
    conv.last_message_at, conv.last_preview, conv.unread = msg.at, text[:255], 0
    if conv.assignee_id is None:
        conv.assignee_id = actor.id
    if contact.lead_id:
        lead = await db.get(Lead, contact.lead_id)
        if lead:
            lead.last_activity_at = now()
            if lead.owner_id is None:
                lead.owner_id = actor.id  # first responder brought the lead in (KPI basis)
            if lead.assignee_id is None:
                lead.assignee_id = actor.id
            from app.services.crm import move, stage_by_code

            st = await db.get(LeadStage, lead.stage_id)
            contacted = await stage_by_code(db, "main", "contacted")
            if st and st.code == "new" and contacted:
                await move(db, lead, contacted, actor.id, "Ответили в " + ("WhatsApp" if conv.channel == "whatsapp" else "Instagram"))
    await db.flush()
    return msg


@router.post("/inbox/conversations/{conv_id}/messages", response_model=MessageOut, status_code=201)
async def reply(conv_id: int, body: SendIn, db: DB, actor: Actor = require("inbox", "reply")) -> MessageOut:
    conv = await _get(db, actor, conv_id, "reply")
    if not in_window(conv):
        # Meta only allows free-form replies within 24h of the client's last message.
        raise conflict("Прошло больше 24 часов с последнего сообщения клиента — отправьте шаблон")
    msg = await _send(db, actor, conv, body.text)
    await write_audit(db, actor_id=actor.id, action="inbox.reply", entity="conversation", entity_id=conv.id,
                      branch_id=conv.branch_id, ip=actor.ip)
    await db.commit()
    return MessageOut.model_validate(msg)


class TemplateIn(BaseModel):
    code: str
    variables: dict = {}


@router.post("/inbox/conversations/{conv_id}/template", response_model=MessageOut, status_code=201)
async def send_template(conv_id: int, body: TemplateIn, db: DB, actor: Actor = require("inbox", "reply")) -> MessageOut:
    conv = await _get(db, actor, conv_id, "reply")
    if conv.channel != "whatsapp":
        raise bad_request("Шаблоны есть только в WhatsApp")
    tpl = await get_template(db, body.code, "ru")
    if tpl is None:
        raise not_found("Шаблон")
    text = render(tpl.body, body.variables)
    contact = await db.get(ExternalContact, conv.contact_id)
    res = await meta.wa_send_template(contact.external_id, tpl.wa_template_name or tpl.code, "ru", list(map(str, body.variables.values())))
    msg = ExternalMessage(conversation_id=conv.id, at=now(), direction="out", external_message_id=res.external_id, kind="template",
                          text=text, status="sent" if res.ok else "failed", error=res.error, sender_id=actor.id)
    db.add(msg)
    conv.last_message_at, conv.last_preview = msg.at, text[:255]
    await db.commit()
    return MessageOut.model_validate(msg)


class ConvPatch(BaseModel):
    assignee_id: int | None = None
    status: str | None = Field(default=None, pattern="^(open|closed)$")
    branch_id: int | None = None


@router.patch("/inbox/conversations/{conv_id}", response_model=ConversationOut)
async def patch_conv(conv_id: int, body: ConvPatch, db: DB, actor: Actor = require("inbox", "reply")) -> ConversationOut:
    conv = await _get(db, actor, conv_id, "reply")
    data = body.model_dump(exclude_unset=True)
    if "branch_id" in data and data["branch_id"]:
        actor.ensure_branch("inbox", "reply", data["branch_id"])
    for k, v in data.items():
        setattr(conv, k, v)
    if "branch_id" in data:
        contact = await db.get(ExternalContact, conv.contact_id)
        if contact.lead_id:
            lead = await db.get(Lead, contact.lead_id)
            lead.branch_id = data["branch_id"]
    if "assignee_id" in data:
        contact = await db.get(ExternalContact, conv.contact_id)
        if contact.lead_id:
            (await db.get(Lead, contact.lead_id)).assignee_id = data["assignee_id"]
    await write_audit(db, actor_id=actor.id, action="inbox.update", entity="conversation", entity_id=conv.id,
                      branch_id=conv.branch_id, ip=actor.ip, after=data)
    await db.commit()
    return await _out(db, actor, conv)
