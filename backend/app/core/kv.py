"""Tiny key-value layer for OTP codes and rate limits: Redis in dev/prod, memory in tests."""

import time

from app.core.config import get_settings


class MemoryKV:
    def __init__(self) -> None:
        self._data: dict[str, tuple[str, float]] = {}

    def _alive(self, key: str) -> str | None:
        item = self._data.get(key)
        if item is None:
            return None
        if item[1] < time.monotonic():
            self._data.pop(key, None)
            return None
        return item[0]

    async def get(self, key: str) -> str | None:
        return self._alive(key)

    async def set(self, key: str, value: str, ttl: int) -> None:
        self._data[key] = (value, time.monotonic() + ttl)

    async def delete(self, key: str) -> None:
        self._data.pop(key, None)

    async def incr(self, key: str, ttl: int) -> int:
        current = self._alive(key)
        if current is None:
            self._data[key] = ("1", time.monotonic() + ttl)
            return 1
        value = int(current) + 1
        self._data[key] = (str(value), self._data[key][1])
        return value

    def clear(self) -> None:
        self._data.clear()


class RedisKV:
    def __init__(self, url: str) -> None:
        import redis.asyncio as redis

        self._r = redis.from_url(url, decode_responses=True)

    async def get(self, key: str) -> str | None:
        return await self._r.get(key)

    async def set(self, key: str, value: str, ttl: int) -> None:
        await self._r.set(key, value, ex=ttl)

    async def delete(self, key: str) -> None:
        await self._r.delete(key)

    async def incr(self, key: str, ttl: int) -> int:
        async with self._r.pipeline() as p:
            p.incr(key)
            p.expire(key, ttl, nx=True)
            value, _ = await p.execute()
        return int(value)


_kv: MemoryKV | RedisKV | None = None


def get_kv() -> MemoryKV | RedisKV:
    global _kv
    if _kv is None:
        s = get_settings()
        _kv = MemoryKV() if s.env == "test" else RedisKV(s.redis_url)
    return _kv
