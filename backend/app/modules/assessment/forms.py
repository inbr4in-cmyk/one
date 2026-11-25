"""«Оценки и анкеты» (owner, 25.11.2026). A form is sections of questions with branching, filled by a link:
open — anyone with the link, no account; closed — signed-in users only. Every sent form is kept like an application.
The answers are seen by the owner and branch admins only (students.archive), never by teachers."""

import secrets
from datetime import date, timedelta

from fastapi import APIRouter, Request
from pydantic import Field
from sqlalchemy import func, select

from app.core.audit import write_audit
from app.core.deps import DB, Actor, CurrentActor, require
from app.core.errors import bad_request, conflict, forbidden, not_found
from app.core.ratelimit import client_ip, hit
from app.core.schemas import In
from app.core.security import normalize_phone
from app.models import Branch, Form, FormResponse, Role, User
from app.services import crm, retention
from app.services.clock import local_range, now, today
from app.services.form_data import ALERT_BELOW, FEEDBACK

router = APIRouter(tags=["forms"])
ADMIN = ("students", "archive")


async def _ensure(db: DB) -> None:
    """The school's own form is there from the first look at the page."""
    if await db.scalar(select(Form.id).where(Form.code == FEEDBACK["code"])) is None:
        db.add(Form(code=FEEDBACK["code"], title=FEEDBACK["title"], description=FEEDBACK["description"], thanks=FEEDBACK["thanks"],
                    token=secrets.token_urlsafe(12), is_open=True, is_active=True, sections=FEEDBACK["sections"]))
        await db.flush()


def _scoped(q, actor: Actor):
    allowed = actor.branches_for(*ADMIN)
    return q if allowed is None else q.where(FormResponse.branch_id.in_(allowed))


def _form_out(f: Form, total: int = 0, new: int = 0) -> dict:
    return {"id": f.id, "title": f.title, "description": f.description, "is_open": f.is_open, "is_active": f.is_active,
            "path": f"/f/{f.token}", "questions": sum(len(s["questions"]) for s in f.sections), "sections": len(f.sections),
            "total": total, "new": new}


@router.get("/forms")
async def forms(db: DB, actor: Actor = require(*ADMIN)) -> list[dict]:
    await _ensure(db)
    await db.commit()
    out = []
    for f in await db.scalars(select(Form).where(Form.archived_at.is_(None)).order_by(Form.id)):
        base = _scoped(select(func.count()).select_from(FormResponse).where(FormResponse.form_id == f.id), actor)
        out.append(_form_out(f, await db.scalar(base) or 0, await db.scalar(base.where(FormResponse.status == "new")) or 0))
    return out


class FormPatch(In):
    is_open: bool | None = None
    is_active: bool | None = None


@router.patch("/forms/{form_id}")
async def patch_form(form_id: int, body: FormPatch, db: DB, actor: Actor = require(*ADMIN)) -> dict:
    """Open ↔ closed, on ↔ off: one form serves the whole school, so only who sees every branch changes it."""
    if actor.branches_for(*ADMIN) is not None:
        raise forbidden("Менять анкету может только администратор сети")
    f = await db.get(Form, form_id)
    if f is None or f.archived_at:
        raise not_found("Анкета")
    before = {"is_open": f.is_open, "is_active": f.is_active}
    if body.is_open is not None:
        f.is_open = body.is_open
    if body.is_active is not None:
        f.is_active = body.is_active
    await write_audit(db, actor_id=actor.id, action="form.update", entity="form", entity_id=f.id, ip=actor.ip, before=before,
                      after={"is_open": f.is_open, "is_active": f.is_active})
    await db.commit()
    return _form_out(f)


# ---------- filling ----------
async def _by_token(db: DB, token: str) -> Form:
    f = await db.scalar(select(Form).where(Form.token == token, Form.archived_at.is_(None))) if 8 <= len(token) <= 40 else None
    if f is None:
        raise not_found("Анкета")
    return f


async def _people(db: DB) -> tuple[list[dict], list[dict]]:
    branches = [{"id": b.id, "name": b.name} for b in await db.scalars(select(Branch).where(Branch.archived_at.is_(None)).order_by(Branch.id))]
    staff = await retention._with_role(db, Role.code == "teacher")
    names = dict((await db.execute(select(User.id, User.full_name).where(User.id.in_([u for u, _ in staff] or [-1])))).all())
    teachers = sorted(({"id": u, "name": names.get(u, ""), "branch_ids": sorted(br)} for u, br in staff), key=lambda x: x["name"])
    return branches, teachers


async def _public(db: DB, f: Form) -> dict:
    branches, teachers = await _people(db)
    return {"title": f.title, "description": f.description, "thanks": f.thanks, "active": f.is_active, "sections": f.sections,
            "branches": branches, "teachers": teachers}


def _route(f: Form, answers: dict) -> list[dict]:
    """The sections this person goes through: an answer may send him to another section."""
    by_id = {s["id"]: s for s in f.sections}
    order = [s["id"] for s in f.sections]
    path, cur, seen = [], order[0] if order else None, set()
    while cur and cur in by_id and cur not in seen:
        s = by_id[cur]
        seen.add(cur)
        path.append(s)
        nxt = s.get("next")
        for q in s["questions"]:
            a = answers.get(q["id"])
            if q["kind"] == "single" and isinstance(a, int) and 0 <= a < len(q["options"]) and q["options"][a].get("goto"):
                nxt = q["options"][a]["goto"]
        if nxt is None:
            i = order.index(cur)
            nxt = order[i + 1] if i + 1 < len(order) else None
        cur = nxt
    return path


def _text(v, limit: int) -> str | None:
    return (v.strip()[:limit] or None) if isinstance(v, str) else None


async def _clean(db: DB, f: Form, raw: dict) -> tuple[dict, dict]:
    branches, teachers = await _people(db)
    bids, tids = {b["id"] for b in branches}, {t["id"] for t in teachers}
    out: dict = {}
    meta: dict = {"flags": [], "name": None, "phone": None, "branch_id": None, "teacher_id": None}
    for s in _route(f, raw):
        for q in s["questions"]:
            a, kind, v = raw.get(q["id"]), q["kind"], None
            if kind in ("short", "para"):
                v = _text(a, 200 if kind == "short" else 2000)
            elif kind == "phone":
                v = _text(a, 30)
                if v:
                    v = normalize_phone(v)
                    if len(v) != 12:
                        raise bad_request("Проверьте номер телефона")
            elif kind in ("single", "select"):
                v = a if isinstance(a, int) and not isinstance(a, bool) and 0 <= a < len(q["options"]) else None
                if v is not None and q["options"][v].get("alert"):
                    meta["flags"].append(q["options"][v]["text"])
            elif kind == "multi":
                if isinstance(a, dict):
                    picked = sorted({i for i in a.get("picked") or [] if isinstance(i, int) and 0 <= i < len(q["options"])})
                    other = _text(a.get("other"), 300) if q.get("other") else None
                    v = {"picked": picked, "other": other} if picked or other else None
            elif kind == "scale":
                v = a if isinstance(a, int) and not isinstance(a, bool) and q["min"] <= a <= q["max"] else None
                if v is not None and v < ALERT_BELOW:
                    meta["flags"].append(f"Оценка {v}: {q['text']}")
            elif kind == "branch":
                v = a if a in bids else None
                meta["branch_id"] = v
            elif kind == "teacher":
                v = a if a in tids else None
                meta["teacher_id"] = v
            if v is None:
                if q.get("required"):
                    raise bad_request(f"Ответьте на вопрос: {q['text']}")
                continue
            out[q["id"]] = v
            if q.get("role") in ("name", "phone"):
                meta[q["role"]] = v
    return out, meta


class SendIn(In):
    answers: dict[str, int | str | dict | None] = Field(max_length=200)


async def _save(db: DB, f: Form, body: SendIn, user_id: int | None) -> dict:
    if not f.is_active:
        raise conflict("Анкета сейчас закрыта")
    answers, meta = await _clean(db, f, body.answers)
    r = FormResponse(form_id=f.id, at=now(), user_id=user_id, answers=answers, flags=meta["flags"][:20], name=meta["name"],
                     phone=meta["phone"], branch_id=meta["branch_id"], teacher_id=meta["teacher_id"])
    db.add(r)
    await db.flush()
    if r.flags:
        for uid in await retention.branch_admins(db, r.branch_id):
            await crm.alert(db, uid, "form", f"Анкета: позвоните {r.name or 'ученику'} сегодня", body="; ".join(r.flags)[:300],
                            link=f"/forms?r={r.id}")
    await db.commit()
    return {"ok": True, "thanks": f.thanks}


@router.get("/public/forms/{token}")
async def public_form(token: str, db: DB) -> dict:
    f = await _by_token(db, token)
    if not f.is_open:
        return {"title": f.title, "closed": True}
    return await _public(db, f)


@router.post("/public/forms/{token}", status_code=201)
async def public_send(token: str, body: SendIn, request: Request, db: DB) -> dict:
    await hit(f"form:{client_ip(request)}", 40, 3600)  # a whole class may share the school Wi-Fi
    f = await _by_token(db, token)
    if not f.is_open:
        raise forbidden("Анкета доступна только после входа")
    return await _save(db, f, body, None)


@router.get("/my/forms")
async def my_forms(db: DB, actor: CurrentActor) -> list[dict]:
    """Forms a signed-in person can fill (shown in the student's and parent's cabinet)."""
    return [{"title": f.title, "path": f"/f/{f.token}"}
            for f in await db.scalars(select(Form).where(Form.archived_at.is_(None), Form.is_active.is_(True)).order_by(Form.id))]


@router.get("/my/forms/{token}")
async def my_form(token: str, db: DB, actor: CurrentActor) -> dict:
    return await _public(db, await _by_token(db, token))


@router.post("/my/forms/{token}", status_code=201)
async def my_send(token: str, body: SendIn, db: DB, actor: CurrentActor) -> dict:
    await hit(f"form:u{actor.id}", 10, 3600)
    return await _save(db, await _by_token(db, token), body, actor.id)


# ---------- the answers: the owner and branch admins only ----------
def _show(q: dict, v, branches: dict, teachers: dict) -> str:
    kind = q["kind"]
    if kind in ("single", "select"):
        return q["options"][v]["text"] if isinstance(v, int) and 0 <= v < len(q["options"]) else ""
    if kind == "multi":
        parts = [q["options"][i]["text"] for i in v.get("picked", []) if 0 <= i < len(q["options"])]
        return ", ".join(parts + ([f"Другое: {v['other']}"] if v.get("other") else []))
    if kind == "scale":
        return f"{v} из {q['max']}"
    if kind == "branch":
        return branches.get(v, "")
    if kind == "teacher":
        return teachers.get(v, "")
    return str(v)


async def _names(db: DB) -> tuple[dict, dict]:
    branches = dict((await db.execute(select(Branch.id, Branch.name))).all())
    teachers = dict((await db.execute(select(User.id, User.full_name).where(User.kind == "staff"))).all())
    return branches, teachers


def _row(r: FormResponse, f: Form, branches: dict, teachers: dict, full: bool) -> dict:
    out = {"id": r.id, "at": r.at, "name": r.name, "phone": r.phone, "branch_id": r.branch_id, "branch": branches.get(r.branch_id),
           "teacher": teachers.get(r.teacher_id), "flags": r.flags, "status": r.status, "note": r.note, "done_at": r.done_at,
           "kind": next((s["title"] for s in f.sections[1:-1] if any(q["id"] in r.answers for q in s["questions"])), None)}
    if full:
        out["sections"] = [{"title": s["title"], "items": [{"text": q["text"], "value": _show(q, r.answers[q["id"]], branches, teachers),
                                                             "low": q["kind"] == "scale" and r.answers[q["id"]] < ALERT_BELOW}
                                                            for q in s["questions"] if q["id"] in r.answers]}
                           for s in f.sections if any(q["id"] in r.answers for q in s["questions"])]
    return out


@router.get("/forms/{form_id}/responses")
async def responses(form_id: int, db: DB, actor: Actor = require(*ADMIN), status: str | None = None, branch_id: int | None = None,
                    limit: int = 200) -> list[dict]:
    f = await db.get(Form, form_id)
    if f is None:
        raise not_found("Анкета")
    q = _scoped(select(FormResponse).where(FormResponse.form_id == f.id), actor)
    if status in ("new", "done"):
        q = q.where(FormResponse.status == status)
    if branch_id:
        q = q.where(FormResponse.branch_id == branch_id)
    branches, teachers = await _names(db)
    return [_row(r, f, branches, teachers, False) for r in await db.scalars(q.order_by(FormResponse.id.desc()).limit(min(max(limit, 1), 500)))]


async def _one(db: DB, actor: Actor, response_id: int) -> tuple[FormResponse, Form]:
    r = await db.scalar(_scoped(select(FormResponse).where(FormResponse.id == response_id), actor))
    if r is None:
        raise not_found("Ответ")
    return r, await db.get(Form, r.form_id)


@router.get("/form-responses/{response_id}")
async def response(response_id: int, db: DB, actor: Actor = require(*ADMIN)) -> dict:
    r, f = await _one(db, actor, response_id)
    return _row(r, f, *await _names(db), True)


class DoneIn(In):
    done: bool = True
    note: str | None = Field(default=None, max_length=1000)


@router.post("/form-responses/{response_id}/done")
async def done(response_id: int, body: DoneIn, db: DB, actor: Actor = require(*ADMIN)) -> dict:
    r, f = await _one(db, actor, response_id)
    r.status = "done" if body.done else "new"
    r.done_by, r.done_at = (actor.id, now()) if body.done else (None, None)
    r.note = (body.note or "").strip() or None
    await write_audit(db, actor_id=actor.id, action="form.response_done", entity="form_response", entity_id=r.id,
                      branch_id=r.branch_id, ip=actor.ip, after={"status": r.status})
    await db.commit()
    return _row(r, f, *await _names(db), True)


@router.get("/forms/{form_id}/summary")
async def summary(form_id: int, db: DB, actor: Actor = require(*ADMIN), date_from: date | None = None,
                  date_to: date | None = None) -> dict:
    """How the answers split by branch: counts for the choice questions, the average for the scales."""
    f = await db.get(Form, form_id)
    if f is None:
        raise not_found("Анкета")
    d2 = date_to or today()
    d1 = date_from or d2 - timedelta(days=30)
    if d1 > d2 or (d2 - d1).days > 366:
        raise bad_request("Период — не больше года")
    start, end = local_range(d1, d2)
    rows = list(await db.scalars(_scoped(select(FormResponse).where(FormResponse.form_id == f.id, FormResponse.at >= start,
                                                                     FormResponse.at < end), actor)))
    out = []
    for s in f.sections:
        for q in s["questions"]:
            if q["kind"] in ("single", "select", "multi"):
                opts = [{"text": o["text"], "total": 0, "by_branch": {}} for o in q["options"]]
                if q.get("other"):
                    opts.append({"text": "Другое", "total": 0, "by_branch": {}})
                for r in rows:
                    v = r.answers.get(q["id"])
                    picked = [v] if isinstance(v, int) else (v.get("picked", []) + ([len(q["options"])] if v.get("other") else [])) if isinstance(v, dict) else []
                    for i in picked:
                        if i < len(opts):
                            opts[i]["total"] += 1
                            opts[i]["by_branch"][str(r.branch_id or 0)] = opts[i]["by_branch"].get(str(r.branch_id or 0), 0) + 1
                out.append({"id": q["id"], "section": s["title"], "text": q["text"], "kind": "choice", "options": opts})
            elif q["kind"] == "scale":
                vals = [r.answers[q["id"]] for r in rows if isinstance(r.answers.get(q["id"]), int)]
                out.append({"id": q["id"], "section": s["title"], "text": q["text"], "kind": "scale", "count": len(vals),
                            "avg": round(sum(vals) / len(vals), 1) if vals else None})
    return {"date_from": d1, "date_to": d2, "count": len(rows), "questions": out}
