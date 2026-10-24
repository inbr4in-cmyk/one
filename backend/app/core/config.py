from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="OE_", extra="ignore")

    env: str = "dev"
    database_url: str = "postgresql+asyncpg://oe:oe@localhost:5432/one_english"
    redis_url: str = "redis://localhost:6379/0"

    # JWT. In production this MUST come from the environment (min 32 bytes).
    jwt_secret: str = Field(default="dev-only-change-me-dev-only-change-me", min_length=32)
    jwt_issuer: str = "one-english"
    access_ttl_minutes: int = 15
    refresh_ttl_days: int = 30
    # Staff without 2FA confirmed get a short session and are pushed to set it up.
    require_staff_2fa: bool = True

    cors_origins: list[str] = ["http://localhost:5173"]
    cookie_secure: bool = False

    # Meta (Instagram / WhatsApp Cloud API)
    meta_app_secret: str = "dev-meta-secret"
    meta_verify_token: str = "dev-verify-token"
    wa_phone_number_id: str = ""
    wa_access_token: str = ""
    ig_access_token: str = ""

    storage_dir: str = "storage"
    max_upload_mb: int = 25

    login_rate_per_minute: int = 10
    otp_rate_per_hour: int = 5

    @property
    def is_prod(self) -> bool:
        return self.env == "prod"


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if s.is_prod and s.jwt_secret.startswith("dev-only"):
        raise RuntimeError("OE_JWT_SECRET must be set in production")
    return s
