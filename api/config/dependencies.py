from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from config.logging import get_logger

logger = get_logger(__name__)


# ── API key auth ───────────────────────────────────────────────────────────
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# Security dependency — also module-level for the same reason
api_key_security = Security(api_key_header)


# Database session
# Import SessionLocal here lazily to avoid circular imports
def get_db():
    """
    FastAPI dependency — yields a database session per request.
    Automatically closes the session when the request finishes,
    even if an exception is raised.

    Usage in any router:
        from config.dependencies import get_db
        def my_endpoint(db: Session = Depends(get_db)):
            ...
    """
    from db.session import SessionLocal

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def verify_api_key(api_key: str = api_key_security):
    """
    MVP: validates against a single key from .env
    Production: look up key in the database, check scopes
    """
    from config.settings import settings

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "success": False,
                "message": "X-API-Key header is missing",
                "data": None,
            },
        )
    if api_key != settings.SECRET_KEY:
        logger.warning(f"Invalid API key attempt: {api_key[:8]}...")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "success": False,
                "message": "Invalid API key",
                "data": None,
            },
        )
    return api_key
