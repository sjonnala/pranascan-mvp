"""Application configuration via environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    database_url: str = "sqlite+aiosqlite:///./pranascan_test.db"

    # Security
    secret_key: str = "dev-secret-key-change-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7  # 7 days

    # App
    app_name: str = "PranaScan API"
    version: str = "0.1.0"
    environment: str = "development"
    log_level: str = "info"
    debug: bool = False

    # Consent
    consent_version: str = "1.0"
    deletion_hold_days: int = 30

    # Quality gate thresholds
    min_lighting_score: float = 0.4
    min_motion_score: float = 0.95
    min_face_confidence: float = 0.8
    min_audio_snr_db: float = 15.0

    # Latency
    latency_target_ms: int = 15_000  # target: <15s end-to-end scan processing

    # Trend
    trend_lookback_days: int = 7
    trend_alert_threshold_pct: float = 15.0  # % deviation from baseline
    trend_min_baseline_scans: int = 3
    trend_cooldown_hours: int = 48  # suppress re-alerts within this window
    alert_webhook_url: str | None = None  # if set, POST alert payloads here

    # Telegram delivery (optional — feature-flagged)
    telegram_bot_token: str | None = None  # BotFather token; enables Telegram delivery
    telegram_chat_id: str | None = None  # target chat/user ID for alert + report delivery

    # WhatsApp delivery (optional — feature-flagged)
    whatsapp_enabled: bool = False  # master feature flag for WhatsApp Cloud API delivery
    whatsapp_access_token: str | None = None  # Meta access token for Cloud API
    whatsapp_phone_number_id: str | None = None  # WhatsApp Business phone number ID
    whatsapp_recipient_phone: str | None = None  # target phone in E.164 format
    whatsapp_api_version: str = "v20.0"  # Graph API version for Cloud API messaging

    # Agent (background daemon)
    agent_secret_key: str | None = None  # if set, enables POST /internal/agent/run endpoint

    # Rate limiting
    scan_rate_limit_per_hour: int = 20  # max scan sessions a user may create per hour

    # ABHA / ABDM integration
    abha_enabled: bool = False  # Feature flag — False by default; set True to activate
    abha_sandbox: bool = True  # True = sandbox/mock gateway; False = live ABDM gateway
    abha_gateway_url: str = "https://dev.abdm.gov.in/gateway"  # ABDM sandbox base URL
    abha_client_id: str | None = None  # ABDM HIU/HIP client ID (required for live mode)
    abha_client_secret: str | None = None  # ABDM client secret (required for live mode)


import logging as _logging  # noqa: E402

_settings_logger = _logging.getLogger(__name__)


def _warn_insecure_defaults(s: "Settings") -> None:
    if s.environment == "production" and s.secret_key == "dev-secret-key-change-in-production":
        raise RuntimeError(
            "FATAL: SECRET_KEY is set to the default dev value in a production environment. "
            "Set a strong random SECRET_KEY environment variable before starting the server."
        )
    if s.environment != "production" and s.secret_key == "dev-secret-key-change-in-production":
        _settings_logger.warning(
            "Using default dev SECRET_KEY. Set SECRET_KEY env var before deploying to production."
        )


settings = Settings()
_warn_insecure_defaults(settings)
