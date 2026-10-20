from __future__ import annotations

import json
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    env: str = "dev"
    app_name: str = "Vehicle Service Management"
    api_v1_prefix: str = "/api/v1"

    # Runtime connection: MUST be the non-owner app_user so RLS applies.
    database_url: str = (
        "postgresql+asyncpg://app_user:app_password@localhost:5432/vsms"
    )
    # Owner connection used only by Alembic (creates roles/tables/policies).
    migration_database_url: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/vsms"
    )

    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: str = "dev-insecure-change-me"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 20
    refresh_token_days: int = 14

    cors_origins: str = "http://localhost:3000,http://localhost"
    platform_base_domain: str = "localhost"

    rate_limit_enabled: bool = True
    rate_limit_free: int = 60
    rate_limit_pro: int = 300
    rate_limit_enterprise: int = 1200
    login_rate_per_minute: int = 10
    preauth_rate_per_minute: int = 600

    billing_provider: str = "stub"
    paddle_api_key: str = ""
    paddle_webhook_secret: str = ""
    paddle_environment: str = "sandbox"
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""

    # Accounting sync: one provider per deployment. `stub` keeps local dev and
    # tests keyless; OAuth apps need their own client id/secret + redirect URI.
    accounting_provider: str = "stub"
    quickbooks_client_id: str = ""
    quickbooks_client_secret: str = ""
    quickbooks_environment: str = "sandbox"
    quickbooks_redirect_uri: str = ""
    xero_client_id: str = ""
    xero_client_secret: str = ""
    xero_redirect_uri: str = ""

    # SMS (Twilio-compatible REST API). Empty credentials = notifications are
    # recorded in the outbox with status 'skipped' instead of being sent.
    sms_provider: str = "twilio"
    sms_account_sid: str = ""
    sms_auth_token: str = ""
    sms_from_number: str = ""
    sms_api_base: str = "https://api.twilio.com"

    # Email delivery (notifications + campaigns). Host/from empty = skipped.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_security: str = "starttls"  # starttls | ssl | none
    smtp_timeout: float = 10.0

    # Web Push (staff devices). Empty keys = a VAPID keypair is generated once
    # and stored in `push_config` (private key encrypted with the master KEK).
    vapid_public_key: str = ""
    vapid_private_key: str = ""
    vapid_subject: str = ""

    # DVI photo storage (local filesystem, tenant-scoped paths).
    storage_dir: str = "/data/uploads"
    upload_max_bytes: int = 8 * 1024 * 1024

    # Public booking: link used in customer-facing URLs (falls back to the
    # request origin when empty).
    public_app_url: str = ""

    default_region: str = "eu"
    region_database_urls: str = "{}"

    master_kek_b64: str = ""
    byok_enabled: bool = False

    log_level: str = "INFO"
    otel_exporter_otlp_endpoint: str = ""

    signup_enabled: bool = True

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def regions(self) -> dict[str, str]:
        try:
            data = json.loads(self.region_database_urls or "{}")
            return {str(k): str(v) for k, v in data.items()}
        except (ValueError, TypeError):
            return {}

    def plan_rate_limit(self, plan: str) -> int:
        return {
            "free": self.rate_limit_free,
            "pro": self.rate_limit_pro,
            "enterprise": self.rate_limit_enterprise,
        }.get(plan, self.rate_limit_free)


@lru_cache
def get_settings() -> Settings:
    return Settings()
