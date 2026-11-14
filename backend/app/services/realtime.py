"""Event bus for WebSocket clients. Redis pub/sub across API workers; in tests events are collected in memory."""

import json
import logging

from app.core.config import get_settings

log = logging.getLogger("realtime")
sent: list[tuple[str, dict]] = []  # test inspection
_redis = None


def _client():
    global _redis
    if _redis is None:
        import redis.asyncio as redis
        from redis.backoff import ExponentialBackoff
        from redis.exceptions import ConnectionError, TimeoutError
        from redis.retry import Retry

        _redis = redis.from_url(get_settings().redis_url, decode_responses=True, health_check_interval=30,
                                retry=Retry(ExponentialBackoff(cap=1, base=0.05), 3), retry_on_error=[ConnectionError, TimeoutError])
    return _redis


async def publish(channel: str, event: dict) -> None:
    """channel examples: user:12, chat:5, inbox:branch:1"""
    if get_settings().env == "test":
        sent.append((channel, event))
        return
    try:
        await _client().publish(f"oe:{channel}", json.dumps(event, default=str))
    except Exception:  # realtime is best effort; data is already saved
        log.warning("publish failed for %s", channel, exc_info=True)


async def subscribe(channels: list[str]):
    pubsub = _client().pubsub()
    await pubsub.subscribe(*[f"oe:{c}" for c in channels])
    return pubsub


async def sessions_ended(user_id: int, only: list[int] | None = None, keep: int | None = None) -> None:
    """Tell this user's open WebSockets that sessions ended (logout, password change, archive — QA C-5).
    only: just these sessions; keep: every session except this one; neither: all of them."""
    await publish(f"user:{user_id}", {"type": "session.ended", "only": only, "keep": keep})


def ends_session(event: dict, session_id: int) -> bool:
    if event.get("type") != "session.ended":
        return False
    only, keep = event.get("only"), event.get("keep")
    return (only is None or session_id in only) and session_id != keep
