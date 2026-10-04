"""Application configuration.

All secrets come from environment variables only — never hard-coded, never
committed. See .env.example and docs/README-env.md.
"""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from functools import lru_cache


def _env(key: str, default: str | None = None) -> str | None:
    value = os.environ.get(key)
    if value is None:
        return default
    value = value.strip()
    return value or default


def _env_bool(key: str, default: bool = False) -> bool:
    raw = _env(key)
    if raw is None:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


def _env_int(key: str, default: int) -> int:
    raw = _env(key)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    """Runtime settings.

    ``environment`` drives the security posture (secure cookies, HSTS, etc.).
    """

    app_name: str = "Vasool"
    environment: str = "dev"  # dev | staging | prod
    base_url: str = "http://127.0.0.1:8000"
    database_url: str = "sqlite+pysqlite:///./vasool.db"

    # Session / crypto
    session_cookie: str = "vasool_session"
    session_ttl_seconds: int = 60 * 60 * 12
    secret_key: str = ""
    # 32-byte urlsafe base64 key used to encrypt per-merchant gateway secret keys
    field_encryption_key: str = ""

    # Payments: which adapter is live ('razorpay' | 'cashfree' | 'mock')
    payment_provider: str = "mock"
    payment_mode: str = "sandbox"  # sandbox | live
    platform_razorpay_key_id: str = ""
    platform_razorpay_key_secret: str = ""
    platform_cashfree_app_id: str = ""
    platform_cashfree_secret: str = ""
    # Webhook secrets used to verify inbound callbacks (adapter-level)
    razorpay_webhook_secret: str = ""
    cashfree_webhook_secret: str = ""

    # Messaging adapters
    messaging_provider: str = "console"  # console | sms_dlt | whatsapp | email
    sms_api_url: str = ""
    sms_api_key: str = ""
    sms_sender_id: str = ""
    sms_dlt_entity_id: str = ""
    sms_dlt_template_id: str = ""
    whatsapp_api_url: str = ""
    whatsapp_token: str = ""
    whatsapp_phone_number_id: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "no-reply@example.in"

    # Abuse protection
    otp_max_per_phone_per_hour: int = 5
    otp_max_per_ip_per_hour: int = 20
    otp_length: int = 6
    otp_ttl_seconds: int = 300
    otp_max_verify_attempts: int = 5
    login_max_per_ip_per_hour: int = 30
    global_rate_limit_per_minute: int = 240

    # Compliance / ops
    cert_in_report_hours: int = 6
    log_retention_days: int = 180
    backup_dir: str = "./backups"
    enable_hsts: bool = False

    # Business defaults (India)
    default_locale: str = "en"
    supported_locales: tuple[str, ...] = ("en", "hi")
    gst_rate_percent: int = 18
    sac_code_default: str = "998314"
    # MSMED Act s.16: compound interest at three times the RBI-notified bank rate
    msmed_interest_multiplier: int = 3
    rbi_bank_rate_percent: float = 0.0  # UNVERIFIED unless set; see docs/DECISIONS.md
    complaint_window_hours: int = 48  # our own SLA for acknowledging a complaint

    @staticmethod
    def from_env() -> Settings:
        env = _env("APP_ENV", "dev") or "dev"
        secret = _env("SECRET_KEY")
        field_key = _env("FIELD_ENCRYPTION_KEY")
        if not secret:
            # Dev fallback only. Production MUST set SECRET_KEY; main.py refuses
            # to boot in prod/staging without it.
            secret = secrets.token_urlsafe(48)
        if not field_key:
            import base64

            field_key = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
        return Settings(
            app_name=_env("APP_NAME", "Vasool") or "Vasool",
            environment=env,
            base_url=(_env("BASE_URL", "http://127.0.0.1:8000") or "").rstrip("/"),
            database_url=_env("DATABASE_URL", "sqlite+pysqlite:///./vasool.db") or "",
            session_cookie=_env("SESSION_COOKIE", "vasool_session") or "vasool_session",
            session_ttl_seconds=_env_int("SESSION_TTL_SECONDS", 60 * 60 * 12),
            secret_key=secret,
            field_encryption_key=field_key,
            payment_provider=(_env("PAYMENT_PROVIDER", "mock") or "mock").lower(),
            payment_mode=(_env("PAYMENT_MODE", "sandbox") or "sandbox").lower(),
            platform_razorpay_key_id=_env("RAZORPAY_KEY_ID", "") or "",
            platform_razorpay_key_secret=_env("RAZORPAY_KEY_SECRET", "") or "",
            platform_cashfree_app_id=_env("CASHFREE_APP_ID", "") or "",
            platform_cashfree_secret=_env("CASHFREE_SECRET_KEY", "") or "",
            razorpay_webhook_secret=_env("RAZORPAY_WEBHOOK_SECRET", "") or "",
            cashfree_webhook_secret=_env("CASHFREE_WEBHOOK_SECRET", "") or "",
            messaging_provider=(_env("MESSAGING_PROVIDER", "console") or "console").lower(),
            sms_api_url=_env("SMS_API_URL", "") or "",
            sms_api_key=_env("SMS_API_KEY", "") or "",
            sms_sender_id=_env("SMS_SENDER_ID", "") or "",
            sms_dlt_entity_id=_env("SMS_DLT_ENTITY_ID", "") or "",
            sms_dlt_template_id=_env("SMS_DLT_TEMPLATE_ID", "") or "",
            whatsapp_api_url=_env("WHATSAPP_API_URL", "") or "",
            whatsapp_token=_env("WHATSAPP_TOKEN", "") or "",
            whatsapp_phone_number_id=_env("WHATSAPP_PHONE_NUMBER_ID", "") or "",
            smtp_host=_env("SMTP_HOST", "") or "",
            smtp_port=_env_int("SMTP_PORT", 587),
            smtp_user=_env("SMTP_USER", "") or "",
            smtp_password=_env("SMTP_PASSWORD", "") or "",
            smtp_from=_env("SMTP_FROM", "no-reply@example.in") or "",
            otp_max_per_phone_per_hour=_env_int("OTP_MAX_PER_PHONE_PER_HOUR", 5),
            otp_max_per_ip_per_hour=_env_int("OTP_MAX_PER_IP_PER_HOUR", 20),
            otp_ttl_seconds=_env_int("OTP_TTL_SECONDS", 300),
            otp_max_verify_attempts=_env_int("OTP_MAX_VERIFY_ATTEMPTS", 5),
            login_max_per_ip_per_hour=_env_int("LOGIN_MAX_PER_IP_PER_HOUR", 30),
            global_rate_limit_per_minute=_env_int("GLOBAL_RATE_LIMIT_PER_MINUTE", 240),
            backup_dir=_env("BACKUP_DIR", "./backups") or "./backups",
            enable_hsts=_env_bool("ENABLE_HSTS", env == "prod"),
            rbi_bank_rate_percent=float(_env("RBI_BANK_RATE_PERCENT", "0") or "0"),
            sac_code_default=_env("SAC_CODE_DEFAULT", "998314") or "998314",
        )

    @property
    def is_prod(self) -> bool:
        return self.environment in {"prod", "staging"}

    @property
    def cookie_secure(self) -> bool:
        return self.base_url.startswith("https://") or self.is_prod


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_env()
