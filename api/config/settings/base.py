from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import List


class BaseAppSettings(BaseSettings):
    """
    Shared settings inherited by all environments.
    No defaults that differ between local and production — those
    go in local.py and prod.py respectively.
    """

    # App
    ENVIRONMENT: str
    SECRET_KEY: str
    LOG_LEVEL: str = "info"
    ALLOWED_ORIGINS: str = ""

    # Database
    DATABASE_URL: str

    # Redis
    REDIS_URL: str

    # MinIO
    MINIO_ENDPOINT: str
    MINIO_USER: str
    MINIO_PASSWORD: str
    MINIO_BUCKET: str = "documents"
    MINIO_SECURE: bool = False

    # AI APIs
    ANTHROPIC_API_KEY: str
    AZURE_DOCINT_ENDPOINT: str = ""
    AZURE_DOCINT_KEY: str = ""

    # Derived properties (same across all environments)
    @property
    def allowed_origins_list(self) -> List[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT == "development"

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    # Shared validators
    @field_validator("LOG_LEVEL")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        allowed = {"debug", "info", "warning", "error", "critical"}
        if v.lower() not in allowed:
            raise ValueError(f"LOG_LEVEL must be one of: {allowed}")
        return v.lower()

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        if len(v) < 16:
            raise ValueError("SECRET_KEY must be at least 16 characters")
        return v

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"
        case_sensitive = True
