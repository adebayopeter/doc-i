from pydantic import field_validator

from config.settings.base import BaseAppSettings


class ProdSettings(BaseAppSettings):
    """
    Production settings.
    Strict security, no debug output, HTTPS enforced.
    All values must come from environment variables — no .env file on the server.
    """

    ENVIRONMENT: str = "production"
    LOG_LEVEL: str = "info"  # no debug noise in prod
    MINIO_SECURE: bool = True  # TLS required in prod

    # Production-only validators
    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key_prod(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError(
                "SECRET_KEY must be at least 32 characters in production. "
                "Generate one with: openssl rand -hex 32"
            )
        if v == "dev-secret-change-this-before-production":
            raise ValueError(
                "You are using the default dev SECRET_KEY in production. "
                "This is a security risk — generate a real key."
            )
        return v

    @field_validator("ANTHROPIC_API_KEY")
    @classmethod
    def validate_anthropic_key(cls, v: str) -> str:
        if not v or v.startswith("sk-ant-xxx"):
            raise ValueError("A real ANTHROPIC_API_KEY is required in production")
        return v

    @field_validator("ALLOWED_ORIGINS")
    @classmethod
    def validate_origins(cls, v: str) -> str:
        if not v:
            raise ValueError(
                "ALLOWED_ORIGINS must be set in production. "
                "e.g. Use * for demo or https://yourdomain.com for production."
            )
        # Allow wildcard for demo deployments
        if v.strip() == "*":
            return v
        origins = [o.strip() for o in v.split(",")]
        for origin in origins:
            if not origin.startswith("https://"):
                raise ValueError(
                    f"All production origins must use HTTPS. Got: {origin}"
                )
        return v

    @field_validator("CLAUDE_MODEL")
    @classmethod
    def validate_claude_model_prod(cls, v: str) -> str:
        if not v or "claude" not in v.lower():
            raise ValueError(
                "CLAUDE_MODEL must be a valid Claude model identifier "
                "e.g. claude-sonnet-4-20250514"
            )
        return v

    class Config(BaseAppSettings.Config):
        env_file = None  # no .env file on the server
        # all vars come from system environment
