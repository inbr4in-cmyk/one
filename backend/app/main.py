import logging

from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.modules import ROUTERS

log = logging.getLogger("app")


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title="One English API",
        version="0.1.0",
        docs_url=None if s.is_prod else "/api/docs",
        openapi_url=None if s.is_prod else "/api/openapi.json",
        redoc_url=None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-Requested-With", "X-Client", "Accept-Language"],
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

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        # Never leak stack traces or SQL to clients.
        log.exception("Unhandled error on %s", request.url.path)
        return JSONResponse({"detail": "Внутренняя ошибка сервера"}, status_code=500)

    api = APIRouter(prefix="/api")
    for r in ROUTERS:
        api.include_router(r)

    @api.get("/health", tags=["system"])
    async def health() -> dict:
        return {"ok": True}

    app.include_router(api)
    return app


app = create_app()
