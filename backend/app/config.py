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


settings = Settings()
