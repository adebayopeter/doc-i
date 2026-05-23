import os

from config.logging import get_logger
from config.settings.base import BaseAppSettings

logger = get_logger(__name__)

_environment = os.getenv("ENVIRONMENT", "development").lower()


def _get_settings() -> BaseAppSettings:
    if _environment == "production":
        from config.settings.prod import ProdSettings

        logger.info("Loaded: production settings")
        return ProdSettings()
    elif _environment == "development":
        from config.settings.local import LocalSettings

        logger.info("Loaded: local/development settings")
        return LocalSettings()
    else:
        raise ValueError(
            f"Unknown ENVIRONMENT='{_environment}'. "
            f"Must be 'development' or 'production'."
        )


settings: BaseAppSettings = _get_settings()

__all__ = ["settings"]
