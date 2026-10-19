from pydantic_settings import BaseSettings, SettingsConfigDict


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
    recording_retention_days: int = 365
    app_name: str = "Hafiz API"
    environment: str = "development"
    vapid_public_key: str = ""
    vapid_private_key: str = ""
    vapid_claims_email: str = "mailto:admin@hafiz.local"


settings = Settings()
