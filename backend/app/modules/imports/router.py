"""Import from the school's old CRM: upload several exports at once, preview (dry run), then commit.

POST /import/old-crm            preview: every row with its status (new / update / skip / error + reason) and totals
POST /import/old-crm?commit=1   the same files again: written file by file, one transaction and one audit entry per file

The kind of each file is detected from its headers; `kinds` overrides it (one entry per file, "" = keep detected).
Files run in dependency order whatever order they were uploaded in: reference data (branches, levels, rooms) →
teachers → groups → students (with parents and group membership) → individual lessons → room schedule →
attendance → payments → books → communications.
"""

import json
import time
from collections import Counter

from fastapi import APIRouter, File, Form, Query, UploadFile
from fastapi.concurrency import run_in_threadpool

from app.core.audit import write_audit
from app.core.config import get_settings
from app.core.deps import DB, Actor, require
from app.core.errors import bad_request, forbidden
from app.core.permissions import NETWORK
from app.models import Branch
from app.modules.imports.parse import KINDS, parse_file
from app.modules.imports.steps import annul_import_money, Ctx, RowResult, build_hints, run_rows, step_refs
from app.services.clock import today

router = APIRouter(tags=["import"])

MAX_FILES = 20


def _totals(rows: list[RowResult]) -> dict:
    c = Counter(r.status for r in rows)
    return {k: c.get(k, 0) for k in ("new", "update", "skip", "error")}


def _rows(rows: list[RowResult]) -> list[dict]:
    return [{"row": r.row, "status": r.status, "label": r.label, "reason": r.reason} for r in rows]


@router.post("/import/old-crm/annul-money")
async def annul_money(db: DB, actor: Actor = require("import", "run"), include_debts: bool = Query(False),
                      commit: bool = Query(False)) -> dict:
    """Preview (commit=false) or cancel the money balances that came from the old CRM. Network-wide owner action."""
    if actor.scope("import", "run") != NETWORK:
        raise forbidden("Только для владельца или администратора сети")
    res = await annul_import_money(db, actor.id, include_debts=include_debts, commit=commit)
    if commit:
        await write_audit(db, actor_id=actor.id, action="import.annul_money", entity="students", ip=actor.ip, after=res)
        await db.commit()
    return res


@router.get("/import/old-crm/kinds")
async def kinds(actor: Actor = require("import", "run")) -> list[dict]:
    return [{"code": k.code, "title": k.title, "order": k.order} for k in sorted(KINDS.values(), key=lambda k: k.order)]


@router.post("/import/old-crm")
async def import_old_crm(
    db: DB,
    actor: Actor = require("import", "run"),
    files: list[UploadFile] = File(...),
    kinds: str | None = Form(None),
    default_branch_id: int | None = Form(None),
    commit: bool = Query(False),
) -> dict:
    if actor.scope("import", "run") != NETWORK:
        raise forbidden("Импорт из старой CRM — только для владельца или администратора сети")
    if not files or len(files) > MAX_FILES:
        raise bad_request(f"От 1 до {MAX_FILES} файлов за раз")
    overrides: list[str] = []
    if kinds:
        try:
            overrides = [str(x or "") for x in json.loads(kinds)]
        except (ValueError, TypeError):
            raise bad_request("kinds: JSON-список типов файлов") from None
        if any(k and k not in KINDS for k in overrides):
            raise bad_request("Неизвестный тип файла")
    if default_branch_id is not None:
        b = await db.get(Branch, default_branch_id)
        if b is None or b.archived_at is not None:
            raise bad_request("Филиал не найден")
    limit = get_settings().import_max_mb * 1024 * 1024
    blobs: list[tuple[str, bytes]] = []
    for f in files:
        data = await f.read(limit + 1)
        if len(data) > limit:
            raise bad_request(f"Файл «{(f.filename or '')[:80]}» больше {get_settings().import_max_mb} МБ")
        blobs.append(((f.filename or "file")[:120], data))
    d = today()

    def parse_all() -> list[dict]:
        return [parse_file(data, name, (overrides[i] if i < len(overrides) else "") or None, d) for i, (name, data) in enumerate(blobs)]

    parsed = await run_in_threadpool(parse_all)
    for i, p in enumerate(parsed):
        p["index"] = i
    batch: dict = {}
    for p in parsed:
        if p["parsed"] is not None:
            batch.setdefault(p["kind"], []).append(p["parsed"])
    ctx = Ctx(db=db, actor=actor, today=d, default_branch_id=default_branch_id, batch=batch)
    build_hints(ctx)
    ordered = sorted((p for p in parsed if p["parsed"] is not None),
                     key=lambda p: (KINDS[p["kind"]].order, -len(p["parsed"].rows), p["index"]))
    out_files: dict[int, dict] = {}
    savepoint = None if commit else await db.begin_nested()

    async def finish(kind: str, title: str, rows: list[RowResult], filename: str | None, stats: dict) -> None:
        if not commit:
            return
        await write_audit(db, actor_id=actor.id, action="import.commit", entity="import", ip=actor.ip,
                          after={"kind": kind, **_totals(rows), **stats},
                          note=f"Импорт из старой CRM: {title}" + (f" — «{filename[:80]}»" if filename else ""))
        await db.commit()

    await ctx.load()
    refs_rows = await step_refs(ctx)
    await finish("refs", "справочники", refs_rows, None, {})
    for p in ordered:
        t0 = time.monotonic()
        await ctx.load()
        before = Counter(ctx.stats)
        try:
            async with db.begin_nested():
                rows = await run_rows(ctx, p["kind"], p["parsed"])
        except Exception as e:  # noqa: BLE001 — the file is rolled back as a whole; the others still go
            ctx.stats = before
            rows = [RowResult(0, "error", p["filename"], f"файл не записан: {type(e).__name__}")]
        stats = dict(Counter(ctx.stats) - before)
        await finish(p["kind"], KINDS[p["kind"]].title, rows, p["filename"], stats)
        out_files[p["index"]] = {"rows": rows, "stats": stats, "ms": int((time.monotonic() - t0) * 1000)}
    if savepoint is not None:
        await savepoint.rollback()

    result_files = []
    for p in parsed:
        done = out_files.get(p["index"])
        rows = done["rows"] if done else []
        result_files.append({
            "index": p["index"], "filename": p["filename"], "kind": p["kind"], "detected": p["detected"],
            "confidence": p["confidence"], "title": KINDS[p["kind"]].title if p["kind"] else None, "header_row": p["header_row"],
            "error": p["error"], "info": (p["parsed"].info if p["parsed"] else {}), "totals": _totals(rows),
            "stats": done["stats"] if done else {}, "ms": done["ms"] if done else 0, "rows": _rows(rows),
        })
    all_rows = refs_rows + [r for f in out_files.values() for r in f["rows"]]
    return {
        "dry_run": not commit,
        "order": [p["index"] for p in ordered],
        "refs": {"totals": _totals(refs_rows), "rows": _rows(refs_rows)},
        "files": result_files,
        "totals": _totals(all_rows),
        "stats": dict(ctx.stats),
    }
