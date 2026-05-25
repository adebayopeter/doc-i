"""
Tests for the configuration layer.
"""

from config.settings import settings
from config.settings.base import BaseAppSettings
from config.settings.local import LocalSettings


def test_settings_is_base_app_settings():
    """settings must be an instance of BaseAppSettings."""
    assert isinstance(settings, BaseAppSettings)


def test_settings_is_local_in_test_environment():
    """In test/development environment LocalSettings must be loaded."""
    assert isinstance(settings, LocalSettings)


def test_settings_environment_is_development():
    assert settings.ENVIRONMENT == "development"


def test_settings_log_level_is_valid():
    valid = {"debug", "info", "warning", "error", "critical"}
    assert settings.LOG_LEVEL in valid


def test_settings_allowed_origins_list_returns_list():
    origins = settings.allowed_origins_list
    assert isinstance(origins, list)
    assert len(origins) > 0


def test_settings_allowed_origins_no_empty_strings():
    for origin in settings.allowed_origins_list:
        assert origin.strip() != ""


def test_settings_is_development_property():
    assert settings.is_development is True
    assert settings.is_production is False


def test_settings_secret_key_minimum_length():
    assert len(settings.SECRET_KEY) >= 16


def test_settings_database_url_not_empty():
    assert settings.DATABASE_URL
    assert settings.DATABASE_URL.startswith("postgresql://")


def test_settings_redis_url_not_empty():
    assert settings.REDIS_URL
    assert settings.REDIS_URL.startswith("redis://")


def test_settings_minio_bucket_has_default():
    assert settings.MINIO_BUCKET == "documents"


def test_settings_azure_keys_default_to_empty():
    """Azure keys are optional — default to empty string."""
    assert isinstance(settings.AZURE_DOCINT_ENDPOINT, str)
    assert isinstance(settings.AZURE_DOCINT_KEY, str)


def test_settings_claude_model_not_empty():
    assert settings.CLAUDE_MODEL
    assert "claude" in settings.CLAUDE_MODEL.lower()


def test_settings_claude_max_tokens_is_positive():
    assert settings.CLAUDE_MAX_TOKENS > 0
    assert isinstance(settings.CLAUDE_MAX_TOKENS, int)
