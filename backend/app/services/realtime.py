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

        _redis = redis.from_url(get_settings().redis_url, decode_responses=True)
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
