"""Taking a test online: what is shared by a group's test at a lesson (sessions.py) and by staff trying a test
themselves (trial.py). A staged test (Test.parts) goes stage by stage, each with its own time, the same order for
everyone; a finished stage cannot be opened again. Correct answers never leave the server."""

import os
from datetime import datetime, timedelta

from sqlalchemy import select

from app.core.config import get_settings
from app.core.deps import DB
from app.core.errors import bad_request
from app.models import Attempt, Question, Test
from app.modules.assessment.router import finalize_final, is_right, score

GRACE = timedelta(seconds=20)  # the page sends the stage itself when its time ends; the network may be slow
VIDEO_MAX = 25 * 1024 * 1024
VIDEO_TYPES = {"video/webm": ".webm", "video/mp4": ".mp4"}


async def questions(db: DB, test_id: int) -> list[Question]:
    return list(await db.scalars(select(Question).where(Question.test_id == test_id, Question.archived_at.is_(None))
                                 .order_by(Question.order, Question.id)))


async def close(db: DB, a: Attempt, t: Test, qs: list[Question], at: datetime) -> None:
    """The attempt ends: score what was answered, remember how long it took. An annulled attempt stays annulled."""
    a.finished_at = at
    a.duration_sec = max(0, int((at - a.started_at).total_seconds()))
    a.auto_score, needs = score(qs, a.answers or {})
    a.score = a.auto_score + (a.manual_score or 0)
    if a.status == "void":
        return
    if needs and a.manual_score is None:
        a.status = "needs_review"
    elif t.kind == "final" and a.student_id:
        await finalize_final(db, a, t, None)
    else:
        a.status = "done"


def stages(t: Test) -> list[dict]:
    return t.parts or []


def total_minutes(t: Test) -> int:
    return sum(int(p["minutes"]) for p in stages(t))


def _end(a: Attempt, part: dict) -> datetime:
    return a.part_started_at + timedelta(minutes=int(part["minutes"]))


async def lapse(db: DB, a: Attempt, t: Test, qs: list[Question], at: datetime) -> None:
    """Stages whose time has run out are left behind, with whatever was saved in them."""
    ps = stages(t)
    if not ps or a.status != "in_progress" or a.finished_at or a.part_started_at is None:
        return
    last = at
    while a.position < len(ps):
        end = _end(a, ps[a.position])
        if at < end + GRACE:
            return
        a.position, a.part_started_at, last = a.position + 1, end, end
    await close(db, a, t, qs, last)


def _clean(q: Question, v):
    if q.kind in ("text", "input"):
        return (v.strip()[:2000] or None) if isinstance(v, str) else None
    if q.kind in ("single", "multi"):
        n = len(q.options or [])
        picked = sorted({i for i in v if isinstance(i, int) and not isinstance(i, bool) and 0 <= i < n}) if isinstance(v, list) else []
        if q.kind == "single":
            picked = picked[:1]
        return picked or None
    return None


async def save(db: DB, a: Attempt, t: Test, qs: list[Question], part_id: str, answers: dict, final: bool, at: datetime) -> None:
    """Answers of the current stage. `final` closes the stage and opens the next one."""
    await lapse(db, a, t, qs, at)
    ps = stages(t)
    if a.status != "in_progress" or a.finished_at or a.position >= len(ps) or ps[a.position]["id"] != part_id:
        return
    merged = dict(a.answers or {})
    for q in qs:
        if q.part != part_id or q.kind == "video" or str(q.id) not in answers:
            continue
        v = _clean(q, answers[str(q.id)])
        if v is None:
            merged.pop(str(q.id), None)
        else:
            merged[str(q.id)] = v
    a.answers = merged
    if final:
        a.position, a.part_started_at = a.position + 1, at
        if a.position >= len(ps):
            await close(db, a, t, qs, at)


def video_path(attempt_id: int, question_id: int, ext: str) -> str:
    folder = os.path.join(get_settings().storage_dir, "test-videos", str(attempt_id))
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, f"{question_id}{ext}")


async def save_video(db: DB, a: Attempt, t: Test, qs: list[Question], question_id: int, content_type: str, data: bytes, at: datetime) -> None:
    """A speaking answer recorded by the camera; kept on the server, seen only by who checks the test."""
    await lapse(db, a, t, qs, at)
    ps = stages(t)
    q = next((x for x in qs if x.id == question_id), None)
    if a.status != "in_progress" or a.finished_at or a.position >= len(ps) or q is None or q.kind != "video" or q.part != ps[a.position]["id"]:
        raise bad_request("Этот вопрос уже закрыт")
    ext = VIDEO_TYPES.get((content_type or "").split(";")[0].strip())
    ok = data[:4] == b"\x1a\x45\xdf\xa3" if ext == ".webm" else data[4:8] == b"ftyp" if ext == ".mp4" else False
    if not ok:
        raise bad_request("Видео не распознано")
    if not 0 < len(data) <= VIDEO_MAX:
        raise bad_request("Видео слишком большое")
    with open(video_path(a.id, q.id, ext), "wb") as f:
        f.write(data)
    a.answers = {**(a.answers or {}), str(q.id): {"video": ext, "size": len(data)}}


def restore(a: Attempt, at: datetime) -> None:
    """«Восстановить»: the person goes on where he stopped; the stage's clock did not run while he was out."""
    if a.voided_at and a.part_started_at:
        a.part_started_at += at - a.voided_at
    a.status, a.voided_at, a.restores = "in_progress", None, a.restores + 1


def stage_state(a: Attempt, t: Test, qs: list[Question]) -> dict | None:
    """The current stage as the person sees it: its questions (no keys), the time it ends, what is already typed."""
    ps = stages(t)
    if a.status != "in_progress" or a.finished_at or a.position >= len(ps):
        return None
    p = ps[a.position]
    mine = [q for q in qs if q.part == p["id"]]
    draft = {str(q.id): (a.answers or {}).get(str(q.id)) for q in mine if str(q.id) in (a.answers or {})}
    return {"id": p["id"], "section": p.get("section"), "title": p.get("title"), "hint": p.get("hint"), "minutes": p["minutes"],
            "text_title": p.get("text_title"), "text": p.get("text"), "audio": p.get("audio"), "words": p.get("words"),
            "seconds": p.get("seconds"), "index": a.position, "total": len(ps), "ends_at": _end(a, p),
            "questions": [{"id": q.id, "kind": q.kind, "text": q.text, "options": q.options or [], "points": q.points} for q in mine],
            "draft": draft}


def outline(t: Test, qs: list[Question]) -> dict:
    """What the person is told before the start."""
    return {"stages": [{"section": p.get("section"), "title": p.get("title"), "minutes": p["minutes"]} for p in stages(t)],
            "minutes": total_minutes(t), "camera": any(q.kind == "video" for q in qs)}


def detail(a: Attempt, t: Test, qs: list[Question]) -> dict:
    """For who checks the test: every answer, whether the key accepts it, and the points given by hand."""
    answers, marks = a.answers or {}, a.marks or {}

    def show(q: Question, v) -> str | None:
        if v is None or q.kind == "video":
            return None
        if q.kind in ("single", "multi"):
            return ", ".join(str((q.options or [])[i]) for i in v if isinstance(i, int) and i < len(q.options or []))
        return str(v)

    def key(q: Question) -> str | None:
        if q.kind == "input":
            return " / ".join(str(x) for x in (q.accept or []))
        if q.kind in ("single", "multi"):
            return ", ".join(str((q.options or [])[i]) for i in (q.correct or []) if i < len(q.options or []))
        return None

    groups = stages(t) or [{"id": None, "section": None, "title": None}]
    out = []
    for p in groups:
        items, got, top = [], 0, 0
        for q in qs:
            if stages(t) and q.part != p["id"]:
                continue
            v = answers.get(str(q.id))
            right = is_right(q, v)
            pts = (q.points if right else 0) if right is not None else marks.get(str(q.id))
            got += pts or 0
            top += q.points
            items.append({"id": q.id, "kind": q.kind, "text": q.text, "points": q.points, "answer": show(q, v), "right": right,
                          "key": key(q), "mark": marks.get(str(q.id)) if right is None else None,
                          "video": bool(isinstance(v, dict) and v.get("video"))})
        out.append({"id": p["id"], "section": p.get("section"), "title": p.get("title"), "score": got, "max": top, "items": items})
    return {"id": a.id, "test_id": t.id, "title": t.title, "taker": a.taker_name, "student_id": a.student_id, "trial": a.trial,
            "status": a.status, "auto_score": a.auto_score, "manual_score": a.manual_score, "score": a.score,
            "max_score": sum(q.points for q in qs), "duration_sec": a.duration_sec, "finished_at": a.finished_at, "parts": out}
