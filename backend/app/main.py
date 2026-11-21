import asyncio
import logging
import re
from urllib.parse import parse_qsl, unquote

from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import DataError, DBAPIError, IntegrityError

from app.core.config import get_settings
from app.modules import ROUTERS

log = logging.getLogger("app")
_BIG_INT = re.compile(r"^-?[0-9]{19,}$")  # beyond int64: no id or count is that long (QA C-7)


def _sqlstate(exc: DBAPIError) -> str:
    err = exc.orig
    for _ in range(3):
        if err is None:
            break
        state = getattr(err, "sqlstate", None) or getattr(err, "pgcode", None)
        if state:
            return str(state)
        err = err.__cause__
    return ""


def _bad_input(detail: str) -> JSONResponse:
    return JSONResponse({"detail": detail}, status_code=422)


class InputGuard:
    """Pure ASGI middleware (QA C-7): rejects NUL bytes anywhere in the URL or a JSON body, and numbers
    in the path or query that no column can hold, before they reach the database as a 500."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path = unquote(scope.get("raw_path", b"").decode("latin-1") or scope["path"])
        query = scope.get("query_string", b"").decode("latin-1")
        values = [v for _, v in parse_qsl(query, keep_blank_values=True)]
        if "\x00" in path or "\x00" in query.lower().replace("%00", "\x00") or any("\x00" in v for v in values):
            return await _bad_input("Недопустимый символ в запросе")(scope, receive, send)
        if any(_BIG_INT.match(p) for p in path.split("/")) or any(_BIG_INT.match(v.strip()) for v in values):
            return await _bad_input("Слишком большое число в запросе")(scope, receive, send)
        headers = dict(scope.get("headers") or [])
        if b"json" not in headers.get(b"content-type", b""):
            return await self.app(scope, receive, send)
        chunks, more = [], True
        while more:
            message = await receive()
            if message["type"] != "http.request":
                return await self.app(scope, _replay([message]), send)
            chunks.append(message.get("body", b""))
            more = message.get("more_body", False)
        body = b"".join(chunks)
        if b"\x00" in body or b"\\u0000" in body:
            return await _bad_input("Недопустимый символ в запросе")(scope, receive, send)
        return await self.app(scope, _replay([{"type": "http.request", "body": body, "more_body": False}], receive), send)


def _replay(messages: list[dict], then=None):
    async def receive():
        if messages:
            return messages.pop(0)
        if then is not None:
            return await then()
        return {"type": "http.disconnect"}

    return receive


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title="One English API",
        version="0.1.0",
        docs_url=None if s.is_prod else "/api/docs",
        openapi_url=None if s.is_prod else "/api/openapi.json",
        redoc_url=None,
    )
    app.add_middleware(InputGuard)  # inside CORS, so its 422 answers still carry CORS headers
    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-Requested-With", "X-Client", "Accept-Language", "Idempotency-Key",
                       "X-Device-Token"],
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        h = response.headers
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("X-Frame-Options", "DENY")
        h.setdefault("Referrer-Policy", "no-referrer")
        h.setdefault("Permissions-Policy", "camera=(), microphone=(self), geolocation=()")
        if request.url.path.startswith("/api/") and "cache-control" not in h:
            h["Cache-Control"] = "no-store"
        if s.is_prod:
            h.setdefault("Strict-Transport-Security", "max-age=63072000; includeSubDomains")
        return response

    @app.exception_handler(DBAPIError)
    async def db_error(request: Request, exc: DBAPIError):
        """QA C-7: a unique/foreign-key violation (SQLSTATE 23…) is a 409, bad data (22…: too long, out of range,
        NUL byte, negative LIMIT) is a 422. Anything else is still a logged 500."""
        state = _sqlstate(exc)
        if isinstance(exc, IntegrityError) or state.startswith("23"):
            log.info("Integrity conflict on %s: %s", request.url.path, state)
            return JSONResponse({"detail": "Такая запись уже есть или связанные данные изменились. Обновите страницу"},
                                status_code=409)
        if isinstance(exc, DataError) or state.startswith("22"):
            log.info("Bad data on %s: %s", request.url.path, state)
            return _bad_input("Некорректные данные: значение слишком длинное, слишком большое или недопустимое")
        log.exception("Database error on %s", request.url.path)
        return JSONResponse({"detail": "Внутренняя ошибка сервера"}, status_code=500)

    from redis.exceptions import ConnectionError as RedisConnectionError
    from redis.exceptions import TimeoutError as RedisTimeoutError

    @app.exception_handler(RedisConnectionError)
    @app.exception_handler(RedisTimeoutError)
    async def redis_down(request: Request, exc: Exception):
        log.error("Redis unavailable on %s", request.url.path)
        return JSONResponse({"detail": "Сервис временно недоступен, попробуйте через минуту"}, status_code=503,
                            headers={"Retry-After": "30"})

    @app.exception_handler(OverflowError)
    async def overflow(request: Request, exc: OverflowError):
        return _bad_input("Слишком большое число")

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        # Never leak stack traces or SQL to clients.
        log.exception("Unhandled error on %s", request.url.path)
        return JSONResponse({"detail": "Внутренняя ошибка сервера"}, status_code=500)

    api = APIRouter(prefix="/api")
    for r in ROUTERS:
        api.include_router(r)

    @api.get("/health", tags=["system"])
    async def health():
        """QA C-12: green only when PostgreSQL and Redis both answer — login and sessions need both."""
        checks = {"db": await _check_db(), "redis": await _check_redis()}
        ok = all(checks.values())
        return JSONResponse({"ok": ok, **checks}, status_code=200 if ok else 503, headers={"Cache-Control": "no-store"})

    app.include_router(api)
    return app


async def _check_db() -> bool:
    from app.core.db import SessionLocal

    try:
        async with asyncio.timeout(3), SessionLocal() as db:
            await db.execute(text("SELECT 1"))
        return True
    except Exception:  # noqa: BLE001 — any failure means «not healthy»
        log.warning("health: database unavailable", exc_info=True)
        return False


async def _check_redis() -> bool:
    from app.core.kv import get_kv

    try:
        async with asyncio.timeout(3):
            return await get_kv().ping()
    except Exception:  # noqa: BLE001
        log.warning("health: redis unavailable", exc_info=True)
        return False


app = create_app()
