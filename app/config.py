import logging

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

_PLACEHOLDER_SECRETS = {"CHANGE_ME_IN_PRODUCTION", "change_me", "changeme", "secret"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+asyncpg://hafiz:hafiz_dev@localhost:5432/hafiz"
    jwt_secret: str = "CHANGE_ME_IN_PRODUCTION"
    jwt_algorithm: str = "HS256"
    parent_token_expire_minutes: int = 60 * 24 * 7
    child_token_expire_minutes: int = 60 * 12
    cors_origins: list[str] = ["http://localhost:5175", "http://127.0.0.1:5175"]
    redis_url: str = "redis://localhost:6380/0"
    s3_endpoint: str = "http://localhost:9002"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket: str = "hafiz-recordings"
    use_local_storage: bool = True
    local_recordings_dir: str = "data/recordings"
    api_public_base: str = "http://localhost:8010"
    recording_retention_days: int = 30
    app_name: str = "Hafiz API"
    environment: str = "development"
    vapid_public_key: str = ""
    vapid_private_key: str = ""
    vapid_claims_email: str = "mailto:admin@hafiz.local"
    # Pra-cek STT: openai (HTTP API) atau faster_whisper (Whisper open source lokal).
    stt_enabled: bool = False
    stt_engine: str = "faster_whisper"  # faster_whisper (gratis) | openai (cloud)
    stt_api_key: str = ""
    stt_base_url: str = "https://api.openai.com/v1"
    stt_model: str = "whisper-1"
    stt_whisper_model: str = "base"  # faster-whisper: tiny, base, small, medium, …
    stt_whisper_device: str = "cpu"  # cpu | cuda
    stt_timeout_seconds: float = 25.0
    # Pengingat
    reminder_timezone: str = "Asia/Jakarta"
    rate_limit_enabled: bool = True
    trust_proxy_headers: bool = False  # true hanya bila di belakang reverse proxy tepercaya

    @model_validator(mode="after")
    def _validate_secrets(self):
        weak_jwt = (
            len(self.jwt_secret) < 32
            or self.jwt_secret in _PLACEHOLDER_SECRETS
            or "change" in self.jwt_secret.lower()
        )
        weak_s3 = (not self.use_local_storage) and self.s3_secret_key == "minioadmin"
        if self.environment.lower() not in ("development", "dev", "test"):
            if weak_jwt:
                raise ValueError("JWT_SECRET lemah atau masih placeholder. Isi dengan string acak minimal 32 karakter.")
            if weak_s3:
                raise ValueError("S3_ACCESS_KEY/S3_SECRET_KEY masih bawaan (minioadmin). Ganti sebelum produksi.")
        elif weak_jwt:
            logger.warning("JWT_SECRET lemah — hanya boleh untuk development.")
        return self


settings = Settings()
