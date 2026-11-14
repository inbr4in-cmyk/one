"""Outbound WhatsApp + in-app notifications with a delivery log and retries (ТЗ 7.2)."""

import re
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.compliance import MessageTemplate, Notification, OutboundMessage
from app.models.identity import User
from app.models.learning import Student, StudentGuardian
from app.services import meta

MAX_ATTEMPTS = 3
_VAR = re.compile(r"\{(\w+)\}")


def render(body: str, variables: dict) -> str:
    return _VAR.sub(lambda m: str(variables.get(m.group(1), m.group(0))), body)


def template_params(body: str, variables: dict) -> list[str]:
    """Values for the Meta template's {{1}}, {{2}}... in the order the {var}s appear in our text."""
    return [str(variables.get(k, "")) for k in _VAR.findall(body)]


async def _deliver(msg: OutboundMessage, text: str) -> None:
    msg.attempts += 1
    wa = (msg.variables or {}).get("wa_template")
    if wa:  # approved Meta template: allowed outside the 24 h window
        res = await meta.wa_send_template(msg.to_phone or "", wa["name"], wa["locale"], wa["params"])
    else:
        res = await meta.wa_send_text(msg.to_phone or "", text)
    if res.ok:
        msg.status, msg.external_id, msg.error = "sent", res.external_id, None
    else:
        msg.status, msg.error = "failed", res.error


async def send_whatsapp_text(
    db: AsyncSession,
    phone: str,
    text: str,
    *,
    template_code: str | None = None,
    to_user_id: int | None = None,
    sensitive: bool = False,
    ref: tuple[str, int] | None = None,
    wa_template: dict | None = None,
) -> OutboundMessage:
    """wa_template = {"name", "locale", "params"}: send the approved Meta template instead of free text."""
    msg = OutboundMessage(
        channel="whatsapp",
        template_code=template_code,
        to_user_id=to_user_id,
        to_phone=phone,
        # One-time codes are never stored in the log.
        body="[скрыто]" if sensitive else text,
        variables={"wa_template": wa_template} if wa_template else {},
        ref_type=ref[0] if ref else None,
        ref_id=ref[1] if ref else None,
    )
    db.add(msg)
    await _deliver(msg, text)
    return msg


async def send_login_code(db: AsyncSession, phone: str, code: str, *, to_user_id: int, locale: str = "ru") -> OutboundMessage:
    """Login code: through the Authentication template when one is configured, else plain text. Never stored."""
    from app.core.config import get_settings

    msg = OutboundMessage(channel="whatsapp", template_code="otp", to_user_id=to_user_id, to_phone=phone, body="[скрыто]",
                          variables={})
    db.add(msg)
    msg.attempts += 1
    name = get_settings().wa_otp_template
    res = (await meta.wa_send_auth_code(phone, name, locale, code) if name
           else await meta.wa_send_text(phone, f"One English: код для входа {code}. Никому его не сообщайте."))
    msg.status, msg.external_id, msg.error = ("sent", res.external_id, None) if res.ok else ("failed", None, res.error)
    return msg


async def notify_user(db: AsyncSession, user_id: int, kind: str, title: str, body: str | None = None,
                      link: str | None = None, meta_: dict | None = None) -> None:
    db.add(Notification(user_id=user_id, at=datetime.now(UTC), kind=kind, title=title, body=body, link=link, meta=meta_ or {}))


async def get_template(db: AsyncSession, code: str, locale: str) -> MessageTemplate | None:
    tpl = await db.scalar(select(MessageTemplate).where(MessageTemplate.code == code, MessageTemplate.locale == locale))
    if tpl is None and locale != "ru":
        tpl = await db.scalar(select(MessageTemplate).where(MessageTemplate.code == code, MessageTemplate.locale == "ru"))
    return tpl


async def notify_guardians(db: AsyncSession, student: Student, code: str, variables: dict,
                           ref: tuple[str, int] | None = None) -> int:
    """Send template `code` to every guardian of the student (WhatsApp + in-app push). Returns sent count."""
    rows = (
        await db.execute(
            select(StudentGuardian, User).join(User, User.id == StudentGuardian.user_id)
            .where(StudentGuardian.student_id == student.id, StudentGuardian.notify.is_(True))
        )
    ).all()
    targets: list[tuple[str, str, int | None]] = [((g.whatsapp or u.phone), u.locale, u.id) for g, u in rows]
    # Adult students without guardians get the message themselves.
    if not targets and student.phone:
        targets = [(student.phone, "ru", student.user_id)]
    sent = 0
    for phone, locale, uid in targets:
        tpl = await get_template(db, code, locale)
        if tpl is None or not tpl.enabled:
            continue
        values = {"name": student.full_name.split(" ")[0], **variables}
        text = render(tpl.body, values)
        wa = ({"name": tpl.wa_template_name, "locale": tpl.locale, "params": template_params(tpl.body, values)}
              if tpl.wa_template_name else None)
        await send_whatsapp_text(db, phone, text, template_code=code, to_user_id=uid, ref=ref, wa_template=wa)
        if uid:
            await notify_user(db, uid, code, text[:120], link=f"/portal/children/{student.id}")
        sent += 1
    return sent


async def retry_failed(db: AsyncSession) -> int:
    rows = await db.scalars(
        select(OutboundMessage).where(OutboundMessage.status == "failed", OutboundMessage.attempts < MAX_ATTEMPTS)
    )
    n = 0
    for msg in rows:
        if msg.body == "[скрыто]":
            continue
        await _deliver(msg, msg.body)
        n += 1
    return n
