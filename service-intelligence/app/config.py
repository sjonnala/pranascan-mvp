"""Application configuration via environment variables."""

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    database_url: str = "sqlite+aiosqlite:///./pranascan_test.db"
    auto_create_tables: bool = False

    # App
    app_name: str = "PranaScan Intelligence API"
    version: str = "0.1.0"
    environment: str = "development"
    debug: bool = False

    # Quality gate thresholds
    min_lighting_score: float = 0.4
    min_motion_score: float = 0.95
    min_face_confidence: float = 0.8
    min_audio_snr_db: float = 15.0
    skip_quality_gate: bool = False

    # Latency
    latency_target_ms: int = 15_000  # target: <15s end-to-end scan processing
    internal_service_token: str = "dev-internal-service-token"

    # gRPC
    grpc_enabled: bool = True
    grpc_host: str = "0.0.0.0"
    grpc_port: int = 50051
    grpc_ssl_key_path: str | None = None
    grpc_ssl_cert_path: str | None = None

    @model_validator(mode='after')
    def validate_production_security(self):
        if self.environment not in ("development", "test") and self.internal_service_token == "dev-internal-service-token":
            raise ValueError("Must override internal_service_token in non-dev environments")
        return self


settings = Settings()
