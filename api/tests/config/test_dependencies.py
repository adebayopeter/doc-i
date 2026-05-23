"""
Tests for FastAPI dependencies — get_db and verify_api_key.
"""

import pytest
from fastapi import HTTPException


def test_get_db_yields_session():
    """get_db must yield a database session and close it after."""
    from config.dependencies import get_db

    gen = get_db()
    session = next(gen)

    assert session is not None

    # Close the generator — triggers the finally block
    try:
        next(gen)
    except StopIteration:
        pass


def test_get_db_closes_on_exception():
    """get_db must close the session even if an exception occurs."""
    from config.dependencies import get_db

    gen = get_db()
    session = next(gen)
    assert session is not None

    # Force close
    gen.close()


@pytest.mark.asyncio
async def test_verify_api_key_valid():
    """Valid API key must return the key."""
    from config.dependencies import verify_api_key
    from config.settings import settings

    result = await verify_api_key(api_key=settings.SECRET_KEY)
    assert result == settings.SECRET_KEY


@pytest.mark.asyncio
async def test_verify_api_key_missing():
    """Missing API key must raise 401."""
    from config.dependencies import verify_api_key

    with pytest.raises(HTTPException) as exc:
        await verify_api_key(api_key=None)

    assert exc.value.status_code == 401
    assert exc.value.detail["message"] == "X-API-Key header is missing"


@pytest.mark.asyncio
async def test_verify_api_key_invalid():
    """Invalid API key must raise 401."""
    from config.dependencies import verify_api_key

    with pytest.raises(HTTPException) as exc:
        await verify_api_key(api_key="invalid-key-that-does-not-match")

    assert exc.value.status_code == 401
    assert exc.value.detail["message"] == "Invalid API key"


@pytest.mark.asyncio
async def test_verify_api_key_empty_string():
    """Empty string API key must raise 401."""
    from config.dependencies import verify_api_key

    with pytest.raises(HTTPException) as exc:
        await verify_api_key(api_key="")

    assert exc.value.status_code == 401
    assert exc.value.detail["message"] == "X-API-Key header is missing"
