import json
import logging
import mimetypes
import secrets

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select

from app.core.audit import write_audit
from app.core.db import SessionLocal
from app.core.deps import DB, Actor, CurrentActor, require
from app.core.errors import bad_request, forbidden, not_found
from app.core.kv import get_kv
from app.core.permissions import NETWORK
from app.core.ratelimit import hit
from app.models import Chat, ChatMember, ChatMessage, Group, GroupMember, Notification, Student, StudentGuardian, User, UserBranch
from app.models.identity import UserKind
from app.services import chats as policy
from app.services import files
from app.services.clock import now
from app.services.realtime import publish, subscribe

log = logging.getLogger("chats")
router = APIRouter(tags=["chats"])


class ChatOut(BaseModel):
    id: int
    kind: str
    title: str
    group_id: int | None
    unread: int
    last_message: dict | None
    other_user: dict | None = None
    members: int = 0


class MessageOut(BaseModel):
    id: int
    chat_id: int
    sender_id: int
    sender_name: str | None
    sender_kind: str | None
    at: str
    kind: str
    text: str | None
    file_url: str | None
    file_name: str | None
    pinned: bool
    edited: bool
    hidden: bool = False


def _msg(m: ChatMessage, users: dict[int, User], show_hidden: bool = False) -> MessageOut:
    u = users.get(m.sender_id)
    hidden = m.hidden_at is not None
    return MessageOut(id=m.id, chat_id=m.chat_id, sender_id=m.sender_id, sender_name=u.full_name if u else None,
                      sender_kind=u.kind if u else None, at=m.at.isoformat(), kind=m.kind,
                      text=None if hidden and not show_hidden else m.text,
                      file_url=None if hidden and not show_hidden else files.signed_url(m.file_url),
                      file_name=m.file_name, pinned=m.pinned, edited=m.edited_at is not None, hidden=hidden)


async def _member(db: DB, chat_id: int, user_id: int) -> ChatMember | None:
    return await db.scalar(select(ChatMember).where(ChatMember.chat_id == chat_id, ChatMember.user_id == user_id,
                                                    ChatMember.left_on.is_(None)))


async def _can_monitor(actor: Actor, chat: Chat) -> bool:
    if not actor.can("chats", "monitor"):
        return False
    return actor.scope("chats", "monitor") == NETWORK or (chat.branch_id in actor.branch_ids)


async def _chat_out(db: DB, chat: Chat, me: int, member: ChatMember | None) -> ChatOut:
    last = await db.scalar(select(ChatMessage).where(ChatMessage.chat_id == chat.id, ChatMessage.hidden_at.is_(None))
                           .order_by(ChatMessage.id.desc()).limit(1))
    unread = 0
    if member:
        unread = await db.scalar(select(func.count()).select_from(ChatMessage).where(
            ChatMessage.chat_id == chat.id, ChatMessage.id > (member.last_read_id or 0), ChatMessage.sender_id != me,
            ChatMessage.hidden_at.is_(None)))
    other = None
    title = chat.title or ""
    if chat.kind == "direct":
        oid = await db.scalar(select(ChatMember.user_id).where(ChatMember.chat_id == chat.id, ChatMember.user_id != me))
        ou = await db.get(User, oid) if oid else None
        if ou:
            other = {"id": ou.id, "full_name": ou.full_name, "kind": ou.kind, "position": ou.position}
            title = ou.full_name
    members = await db.scalar(select(func.count()).select_from(ChatMember).where(ChatMember.chat_id == chat.id,
                                                                                   ChatMember.left_on.is_(None)))
    sender = await db.get(User, last.sender_id) if last else None
    return ChatOut(id=chat.id, kind=chat.kind, title=title, group_id=chat.group_id, unread=unread, other_user=other,
                   members=members,
                   last_message={"text": last.text or ("Файл" if last.file_url else ""), "at": last.at.isoformat(),
                                 "sender": sender.full_name if sender else None} if last else None)


@router.get("/chats", response_model=list[ChatOut])
async def my_chats(db: DB, actor: Actor = require("chats", "use")) -> list[ChatOut]:
    rows = (await db.execute(
        select(Chat, ChatMember).join(ChatMember, ChatMember.chat_id == Chat.id)
        .where(ChatMember.user_id == actor.id, ChatMember.left_on.is_(None))
        .order_by(Chat.last_message_at.desc().nulls_last()).limit(300)
    )).all()
    return [await _chat_out(db, c, actor.id, m) for c, m in rows]


@router.get("/chats/contacts")
async def contacts(db: DB, actor: Actor = require("chats", "use"), q: str | None = None) -> list[dict]:
    """People I'm allowed to start a direct chat with."""
    me = actor.user
    cand: set[int] = set()
    if me.kind == UserKind.STAFF:
        if actor.can("chats", "message_staff"):
            branch_users = select(UserBranch.user_id).where(UserBranch.branch_id.in_(actor.branch_ids or {-1}))
            cand |= set((await db.scalars(branch_users)).all())
        student_ids = []
        for action in ("message_students", "message_parents"):
            if not actor.can("chats", action):
                continue
            scope = actor.scope("chats", action)
            sq = select(Student.id).where(Student.archived_at.is_(None))
            if scope == "own":
                sq = sq.where(Student.id.in_(select(GroupMember.student_id).join(Group, Group.id == GroupMember.group_id)
                                             .where(Group.teacher_id == me.id, GroupMember.left_on.is_(None))))
            elif scope == "branch":
                sq = sq.where(Student.branch_id.in_(actor.branch_ids or {-1}))
            student_ids = list((await db.scalars(sq.limit(2000))).all())
            if action == "message_students":
                cand |= {u for u in (await db.scalars(select(Student.user_id).where(Student.id.in_(student_ids)))).all() if u}
            else:
                cand |= set((await db.scalars(select(StudentGuardian.user_id).where(StudentGuardian.student_id.in_(student_ids)))).all())
    else:
        kids = await policy._students_of_user(db, me)
        kid_ids = [k.id for k in kids]
        teachers = await db.scalars(select(Group.teacher_id).join(GroupMember, GroupMember.group_id == Group.id)
                                    .where(GroupMember.student_id.in_(kid_ids), GroupMember.left_on.is_(None)))
        cand |= set(teachers.all())
        branch_staff = await db.scalars(select(UserBranch.user_id).where(UserBranch.branch_id.in_({k.branch_id for k in kids} or {-1})))
        cand |= set(branch_staff.all())
        if me.kind == UserKind.PARENT:
            cand |= {k.user_id for k in kids if k.user_id}
    cand.discard(me.id)
    out = []
    users = list(await db.scalars(select(User).where(User.id.in_(cand), User.is_active.is_(True), User.archived_at.is_(None))
                                  .order_by(User.full_name).limit(500)))
    for u in users:
        if q and q.lower() not in u.full_name.lower():
            continue
        ok, _ = await policy.direct_allowed(db, me, u)
        if ok:
            out.append({"id": u.id, "full_name": u.full_name, "kind": u.kind, "position": u.position})
    return out[:200]


class DirectIn(BaseModel):
    user_id: int
    about_student_id: int | None = None


@router.post("/chats/direct", response_model=ChatOut)
async def open_direct(body: DirectIn, db: DB, actor: Actor = require("chats", "use")) -> ChatOut:
    other = await db.get(User, body.user_id)
    if other is None or not other.is_active or other.archived_at:
        raise not_found("Пользователь")
    ok, reason = await policy.direct_allowed(db, actor.user, other)
    if not ok:
        await write_audit(db, actor_id=actor.id, action="chat.denied", entity="user", entity_id=other.id, ip=actor.ip, note=reason)
        await db.commit()
        raise forbidden(reason)
    key = policy.direct_key(actor.id, other.id)
    chat = await db.scalar(select(Chat).where(Chat.direct_key == key))
    if chat is None:
        staff = actor.user if actor.is_staff else other
        branch = await db.scalar(select(UserBranch.branch_id).where(UserBranch.user_id == staff.id).limit(1))
        chat = Chat(kind="direct", direct_key=key, branch_id=branch, about_student_id=body.about_student_id, last_message_at=now())
        db.add(chat)
        await db.flush()
        await policy.add_member(db, chat.id, actor.id)
        await policy.add_member(db, chat.id, other.id)
        await db.commit()
    return await _chat_out(db, chat, actor.id, await _member(db, chat.id, actor.id))


async def _open_chat(db: DB, actor: Actor, chat_id: int) -> tuple[Chat, ChatMember | None]:
    chat = await db.get(Chat, chat_id)
    if chat is None:
        raise not_found("Чат")
    m = await _member(db, chat.id, actor.id)
    if m is None and not await _can_monitor(actor, chat):
        raise not_found("Чат")
    return chat, m


@router.get("/chats/{chat_id}/messages", response_model=list[MessageOut])
async def chat_messages(chat_id: int, db: DB, actor: Actor = require("chats", "use"), before_id: int | None = None,
                        after_id: int | None = None, limit: int = Query(50, le=200)) -> list[MessageOut]:
    chat, m = await _open_chat(db, actor, chat_id)
    monitoring = m is None
    q = select(ChatMessage).where(ChatMessage.chat_id == chat.id)
    if before_id:
        q = q.where(ChatMessage.id < before_id)
    if after_id:
        q = q.where(ChatMessage.id > after_id)
    rows = list(await db.scalars(q.order_by(ChatMessage.id.desc()).limit(limit)))
    users = {u.id: u for u in await db.scalars(select(User).where(User.id.in_({r.sender_id for r in rows})))} if rows else {}
    if monitoring:
        # Quality-control viewing is read-only and every view is logged.
        await write_audit(db, actor_id=actor.id, action="chat.monitor_view", entity="chat", entity_id=chat.id,
                          branch_id=chat.branch_id, ip=actor.ip)
        await db.commit()
    elif rows and not before_id:
        m.last_read_id = max(m.last_read_id or 0, rows[0].id)
        await db.commit()
    return [_msg(r, users, show_hidden=monitoring) for r in reversed(rows)]


class SendIn(BaseModel):
    text: str | None = Field(default=None, max_length=4000)
    file_key: str | None = None
    file_name: str | None = Field(default=None, max_length=255)
    kind: str = Field(default="text", pattern="^(text|image|file|voice)$")


@router.post("/chats/{chat_id}/messages", response_model=MessageOut, status_code=201)
async def send(chat_id: int, body: SendIn, db: DB, actor: Actor = require("chats", "use")) -> MessageOut:
    chat, m = await _open_chat(db, actor, chat_id)
    if m is None:
        raise forbidden("Просмотр чата только для чтения")
    if not (body.text and body.text.strip()) and not body.file_key:
        raise bad_request("Пустое сообщение")
    if body.file_key and not files.path_of(body.file_key):
        raise bad_request("Файл не найден")
    await hit(f"chat-send:{actor.id}", 60, 60)
    if chat.kind == "direct":
        # Rules can change (a student leaves a group): re-check on every send.
        oid = await db.scalar(select(ChatMember.user_id).where(ChatMember.chat_id == chat.id, ChatMember.user_id != actor.id))
        other = await db.get(User, oid) if oid else None
        ok, reason = (await policy.direct_allowed(db, actor.user, other)) if other else (False, "Собеседник недоступен")
        if not ok:
            raise forbidden(reason)
    msg = ChatMessage(chat_id=chat.id, sender_id=actor.id, at=now(), kind=body.kind, text=(body.text or "").strip() or None,
                      file_url=body.file_key, file_name=body.file_name)
    db.add(msg)
    chat.last_message_at = msg.at
    await db.flush()
    m.last_read_id = msg.id
    await db.commit()
    out = _msg(msg, {actor.id: actor.user})
    member_ids = (await db.scalars(select(ChatMember.user_id).where(ChatMember.chat_id == chat.id, ChatMember.left_on.is_(None)))).all()
    for uid in member_ids:
        await publish(f"user:{uid}", {"type": "chat.message", "chat_id": chat.id, "message": out.model_dump()})
    return out


@router.post("/chats/{chat_id}/read", status_code=204)
async def mark_read(chat_id: int, db: DB, actor: Actor = require("chats", "use")) -> None:
    chat, m = await _open_chat(db, actor, chat_id)
    if m:
        m.last_read_id = await db.scalar(select(func.max(ChatMessage.id)).where(ChatMessage.chat_id == chat.id)) or 0
        await db.commit()


@router.post("/chat-messages/{message_id}/pin", response_model=MessageOut)
async def pin(message_id: int, db: DB, actor: Actor = require("chats", "pin")) -> MessageOut:
    msg = await db.get(ChatMessage, message_id)
    if msg is None:
        raise not_found("Сообщение")
    chat, m = await _open_chat(db, actor, msg.chat_id)
    if m is None or chat.kind != "group":
        raise forbidden("Закреплять можно в своём групповом чате")
    msg.pinned = not msg.pinned
    await db.commit()
    return _msg(msg, {u.id: u for u in [await db.get(User, msg.sender_id)] if u})


@router.get("/chats/{chat_id}/pinned", response_model=list[MessageOut])
async def pinned(chat_id: int, db: DB, actor: Actor = require("chats", "use")) -> list[MessageOut]:
    chat, _ = await _open_chat(db, actor, chat_id)
    rows = list(await db.scalars(select(ChatMessage).where(ChatMessage.chat_id == chat.id, ChatMessage.pinned.is_(True),
                                                           ChatMessage.hidden_at.is_(None)).order_by(ChatMessage.id.desc())))
    users = {u.id: u for u in await db.scalars(select(User).where(User.id.in_({r.sender_id for r in rows})))} if rows else {}
    return [_msg(r, users) for r in rows]


@router.delete("/chat-messages/{message_id}", status_code=204)
async def hide(message_id: int, db: DB, actor: Actor = require("chats", "use")) -> None:
    """Members can hide their own message; it stays stored for quality control (ТЗ 8)."""
    msg = await db.get(ChatMessage, message_id)
    if msg is None or msg.sender_id != actor.id:
        raise not_found("Сообщение")
    msg.hidden_at = now()
    await db.commit()


@router.get("/chats/monitor", response_model=list[ChatOut])
async def monitor_list(db: DB, actor: Actor = require("chats", "monitor"), branch_id: int | None = None,
                       kind: str | None = None) -> list[ChatOut]:
    q = select(Chat)
    if actor.scope("chats", "monitor") != NETWORK:
        q = q.where(Chat.branch_id.in_(actor.branch_ids or {-1}))
    if branch_id:
        q = q.where(Chat.branch_id == branch_id)
    if kind:
        q = q.where(Chat.kind == kind)
    rows = list(await db.scalars(q.order_by(Chat.last_message_at.desc().nulls_last()).limit(200)))
    out = []
    for c in rows:
        o = await _chat_out(db, c, actor.id, None)
        if c.kind == "direct":
            names = (await db.scalars(select(User.full_name).join(ChatMember, ChatMember.user_id == User.id)
                                      .where(ChatMember.chat_id == c.id))).all()
            o.title, o.other_user = " ↔ ".join(names), None
        out.append(o)
    return out


# ---------- files ----------
@router.post("/files", status_code=201)
async def upload(actor: CurrentActor, file: UploadFile = File(...)) -> dict:
    await hit(f"upload:{actor.id}", 30, 300)
    data = await file.read(25 * 1024 * 1024 + 1)
    ctype = (file.content_type or "").split(";")[0].strip()
    if err := files.check(ctype, data[:32], len(data)):
        raise bad_request(err)
    key = files.save(data, ctype)
    return {"key": key, "url": files.signed_url(key), "name": (file.filename or "файл")[:255], "size": len(data)}


@router.get("/files/{key}")
async def download(key: str, exp: int, sig: str):
    if not files.verify(key, exp, sig):
        raise HTTPException(403, "Ссылка устарела")
    path = files.path_of(key)
    if path is None:
        raise not_found("Файл")
    ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
    inline = ctype.startswith(("image/", "audio/", "video/")) or ctype == "application/pdf"
    return FileResponse(path, media_type=ctype, content_disposition_type="inline" if inline else "attachment",
                        headers={"Cache-Control": "private, max-age=600", "X-Content-Type-Options": "nosniff"})


# ---------- notifications ----------
@router.get("/notifications")
async def my_notifications(db: DB, actor: CurrentActor, limit: int = 30) -> dict:
    rows = await db.scalars(select(Notification).where(Notification.user_id == actor.id).order_by(Notification.id.desc()).limit(min(limit, 100)))
    unread = await db.scalar(select(func.count()).select_from(Notification).where(Notification.user_id == actor.id,
                                                                                  Notification.read_at.is_(None)))
    return {"unread": unread, "items": [{"id": n.id, "at": n.at, "kind": n.kind, "title": n.title, "body": n.body,
                                         "link": n.link, "read": n.read_at is not None} for n in rows]}


@router.post("/notifications/read-all", status_code=204)
async def read_all(db: DB, actor: CurrentActor) -> None:
    for n in await db.scalars(select(Notification).where(Notification.user_id == actor.id, Notification.read_at.is_(None))):
        n.read_at = now()
    await db.commit()


@router.get("/counters")
async def counters(db: DB, actor: CurrentActor) -> dict:
    """Badge numbers for the sidebar."""
    out = {"notifications": await db.scalar(select(func.count()).select_from(Notification).where(
        Notification.user_id == actor.id, Notification.read_at.is_(None)))}
    if actor.can("chats", "use"):
        total = 0
        for m in await db.scalars(select(ChatMember).where(ChatMember.user_id == actor.id, ChatMember.left_on.is_(None))):
            total += await db.scalar(select(func.count()).select_from(ChatMessage).where(
                ChatMessage.chat_id == m.chat_id, ChatMessage.id > (m.last_read_id or 0), ChatMessage.sender_id != actor.id,
                ChatMessage.hidden_at.is_(None)))
        out["chats"] = total
    if actor.can("inbox", "view"):
        from app.models import Conversation
        from app.modules.inbox.router import conv_filter

        out["inbox"] = await db.scalar(select(func.count()).select_from(Conversation).where(conv_filter(actor), Conversation.unread > 0))
    return out


# ---------- websocket ----------
@router.post("/ws/ticket")
async def ws_ticket(actor: CurrentActor) -> dict:
    """A one-time, 30-second ticket: the access token never goes into a URL."""
    t = secrets.token_urlsafe(24)
    await get_kv().set(f"ws:{t}", str(actor.id), 30)
    return {"ticket": t}


@router.websocket("/ws")
async def ws(websocket: WebSocket, ticket: str):
    kv = get_kv()
    uid = await kv.get(f"ws:{ticket}")
    await kv.delete(f"ws:{ticket}")
    if not uid:
        await websocket.close(code=4401)
        return
    async with SessionLocal() as db:
        user = await db.get(User, int(uid))
        if user is None or not user.is_active:
            await websocket.close(code=4401)
            return
        from app.core.deps import load_actor

        actor = await load_actor(db, user, 0, True, "")
        channels = [f"user:{user.id}"]
        if actor.can("inbox", "view"):
            scope = actor.scope("inbox", "view")
            from app.models import Branch

            branches = actor.branch_ids if scope != NETWORK else set((await db.scalars(select(Branch.id))).all())
            channels += [f"inbox:branch:{b}" for b in branches]
    await websocket.accept()
    pubsub = await subscribe(channels)
    try:
        import asyncio

        async def pump():
            async for item in pubsub.listen():
                if item.get("type") == "message":
                    await websocket.send_text(item["data"])

        async def keepalive():
            while True:
                msg = await websocket.receive_text()
                if msg == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))

        done, pending = await asyncio.wait([asyncio.create_task(pump()), asyncio.create_task(keepalive())],
                                           return_when=asyncio.FIRST_COMPLETED)
        for t in pending:
            t.cancel()
    except WebSocketDisconnect:
        pass
    finally:
        await pubsub.unsubscribe()
        await pubsub.aclose()


__all__ = ["router", "or_"]
