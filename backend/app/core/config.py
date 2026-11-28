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
    # Fernet key for 2FA secrets at rest. Empty = derived from OE_JWT_SECRET (then rotating that secret resets 2FA).
    totp_key: str = ""

    cors_origins: list[str] = ["http://localhost:5173"]
    cookie_secure: bool = False
    # Set only when the API sits behind our nginx, which overwrites X-Real-IP; otherwise clients could spoof it.
    trust_proxy: bool = False

    # Meta (Instagram / WhatsApp Cloud API)
    meta_app_secret: str = "dev-meta-secret"
    meta_verify_token: str = "dev-verify-token"
    meta_graph_version: str = "v24.0"
    wa_phone_number_id: str = ""
    wa_access_token: str = ""
    # WhatsApp through the provider 360dialog (the number stays in the WhatsApp Business app too): its API key,
    # and the secret 360dialog sends back in a header of every webhook call.
    wa_d360_api_key: str = ""
    wa_d360_webhook_secret: str = ""
    # WhatsApp linked by QR like WhatsApp Web (wa/bridge.mjs on this server): where it listens and the shared secret.
    # Managers' manual answers only; notifications, login codes and templates never go this way.
    wa_bridge_url: str = ""
    wa_bridge_secret: str = ""
    ig_access_token: str = ""
    # «Instagram API with Instagram login»: its webhooks are signed with the Instagram app secret, not the Meta one.
    ig_app_secret: str = ""
    # Who sends: the Facebook Page linked to the school's Instagram, or with a «Unified login» token the Instagram
    # account id itself. Replies go to /{id}/messages. Instagram-login tokens (IG...) use /me/messages.
    ig_page_id: str = ""
    # Facebook / Instagram ads statistics (read only, permission ads_read): the token and the ad account id «act_…».
    ads_access_token: str = ""
    ads_account_id: str = ""
    # Approved WhatsApp Authentication template for login codes (Meta name). Empty = plain text (24 h window only).
    wa_otp_template: str = ""
    # TESTING ONLY: while WhatsApp is not connected, students and parents sign in with this fixed 6-digit code
    # instead of a sent one. Ignored as soon as WhatsApp is configured. Empty = off.
    portal_test_code: str = Field(default="", pattern=r"^(\d{6})?$")

    # Push: Firebase service-account JSON (FCM HTTP v1 serves Android and iOS via APNs). Empty = log only.
    fcm_credentials_file: str = ""

    storage_dir: str = "storage"
    max_upload_mb: int = 25
    import_max_mb: int = 10

    login_rate_per_minute: int = 10
    otp_rate_per_hour: int = 5

    @property
    def is_prod(self) -> bool:
        return self.env in ("prod", "production")


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if s.is_prod:
        problems = [name for name, bad in (
            ("OE_JWT_SECRET", s.jwt_secret.startswith("dev-only")),
            ("OE_META_APP_SECRET", s.meta_app_secret.startswith("dev-") or len(s.meta_app_secret) < 16),
            ("OE_META_VERIFY_TOKEN", s.meta_verify_token.startswith("dev-") or len(s.meta_verify_token) < 16),
            ("OE_COOKIE_SECURE", not s.cookie_secure),
        ) if bad]
        if problems:
            raise RuntimeError("Unsafe production settings: " + ", ".join(problems))
    return s
