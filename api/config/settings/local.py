from config.settings.base import BaseAppSettings


class LocalSettings(BaseAppSettings):
    """
    Local development settings.
    Debug-friendly defaults — verbose logging, CORS wide open,
    no strict security requirements.
    """

    # Dev-specific defaults
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "debug"             # verbose in dev
    MINIO_SECURE: bool = False           # no TLS needed locally

    # Dev CORS — allow Streamlit and any local React dev server
    ALLOWED_ORIGINS: str = (
        "http://localhost:8502,"
        "http://localhost:3000,"
        "http://localhost:5173"          # Vite dev server if you use React later
    )

    class Config(BaseAppSettings.Config):
        env_file = ".env"                # reads your local .env file


settings = LocalSettings()
