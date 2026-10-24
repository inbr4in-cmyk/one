from fastapi import HTTPException, Request, status

from app.core.config import get_settings
from app.core.kv import get_kv


def client_ip(request: Request) -> str:
    # X-Real-IP is trusted only behind our nginx, which always overwrites it.
    if get_settings().trust_proxy and request.headers.get("x-real-ip"):
        return request.headers["x-real-ip"]
    return request.client.host if request.client else "unknown"


async def hit(bucket: str, limit: int, window_s: int) -> None:
    count = await get_kv().incr(f"rl:{bucket}", window_s)
    if count > limit:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Слишком много попыток. Попробуйте позже.",
            headers={"Retry-After": str(window_s)},
        )
