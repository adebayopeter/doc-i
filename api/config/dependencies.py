"""
FastAPI dependency injection for database sessions and authentication.

Auth system supports two modes:
  1. Master SECRET_KEY from .env — super-admin access to everything
  2. Per-process API keys from database — scoped access to specific processes
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session

from config.logging import get_logger

logger = get_logger(__name__)


# ── API key auth ───────────────────────────────────────────────────────────
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# Security dependency — also module-level for the same reason
api_key_security = Security(api_key_header)


@dataclass
class AuthContext:
    """
    Authentication context attached to each request.

    Attributes:
        key_id: Database ID of the API key, or "master" for SECRET_KEY
        name: Human-readable key name
        process_ids: List of process IDs this key can access (empty = all)
        scopes: List of allowed scopes ("read", "write")
        is_admin: True if this key can access all processes
    """

    key_id: str
    name: str
    process_ids: List[str]
    scopes: List[str]
    is_admin: bool


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


async def verify_api_key(
    api_key: str = api_key_security,
    db: Session = Depends(get_db),
) -> AuthContext:
    """
    Verify the API key and return an AuthContext.

    Authentication flow:
      1. Check if key is missing → 401
      2. Check if key matches master SECRET_KEY → return admin context
      3. Look up key by hash in database
      4. If found and active → update usage stats, return context
      5. If expired or inactive → 401 with clear message
      6. If not found → 401

    The master SECRET_KEY from .env always works as a super-admin key
    for backward compatibility and admin operations.
    """
    from config.settings import settings
    from db.models import ApiKey
    from services.api_keys import hash_api_key

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "success": False,
                "message": "X-API-Key header is missing",
                "data": None,
            },
        )

    # Check master SECRET_KEY first (backward compatibility + admin access)
    if api_key == settings.SECRET_KEY:
        logger.debug("Authenticated with master SECRET_KEY")
        return AuthContext(
            key_id="master",
            name="Master Admin Key",
            process_ids=[],
            scopes=["read", "write"],
            is_admin=True,
        )

    # Look up key by hash in database
    key_hash = hash_api_key(api_key)
    key_record = db.query(ApiKey).filter(ApiKey.key_hash == key_hash).first()

    if not key_record:
        logger.warning(f"Invalid API key attempt: {api_key[:12]}...")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "success": False,
                "message": "Invalid API key",
                "data": None,
            },
        )

    # Check if key is active
    if not key_record.is_active:
        logger.warning(f"Disabled API key used: {key_record.key_prefix}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "success": False,
                "message": "This API key has been disabled",
                "data": None,
            },
        )

    # Check expiry
    if key_record.expires_at:
        now = datetime.now(timezone.utc)
        # Handle both timezone-aware and naive datetimes from database
        expires_at = key_record.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at < now:
            logger.warning(f"Expired API key used: {key_record.key_prefix}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "success": False,
                    "message": f"This API key expired on {key_record.expires_at.isoformat()}",
                    "data": None,
                },
            )

    # Update usage statistics
    key_record.last_used_at = datetime.now(timezone.utc)
    key_record.request_count += 1
    db.commit()

    logger.debug(f"Authenticated with key: {key_record.key_prefix} ({key_record.name})")

    return AuthContext(
        key_id=key_record.id,
        name=key_record.name,
        process_ids=key_record.process_ids or [],
        scopes=key_record.scopes or ["read", "write"],
        is_admin=not key_record.process_ids,  # Empty list = admin
    )


def get_auth_context(
    auth: AuthContext = Depends(verify_api_key),
) -> AuthContext:
    """
    Simple passthrough dependency for getting auth context.
    Use this when you need the auth context but don't need to verify process access.
    """
    return auth


def require_admin(
    auth: AuthContext = Depends(verify_api_key),
) -> AuthContext:
    """
    Dependency that requires admin access.

    Use on endpoints that should only be accessible by:
      - Master SECRET_KEY
      - API keys with empty process_ids (admin keys)

    Raises 403 if the key is not an admin key.
    """
    if not auth.is_admin:
        logger.warning(f"Non-admin key {auth.key_id} attempted admin endpoint")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "success": False,
                "message": "This endpoint requires admin access",
                "data": None,
            },
        )
    return auth


def require_scope(required_scope: str):
    """
    Factory for scope-checking dependencies.

    Usage:
        @router.get("/", dependencies=[Depends(require_scope("read"))])
        @router.post("/", dependencies=[Depends(require_scope("write"))])
    """

    def dependency(auth: AuthContext = Depends(verify_api_key)) -> AuthContext:
        from services.api_keys import has_scope

        if not has_scope(auth.scopes, required_scope):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "success": False,
                    "message": f"This API key does not have '{required_scope}' scope",
                    "data": None,
                },
            )
        return auth

    return dependency


class ProcessAccessChecker:
    """
    Dependency class for verifying process access.

    Usage in routers:
        @router.get("/{process_id}")
        def get_process(
            process_id: str,
            auth: AuthContext = Depends(ProcessAccessChecker()),
        ):
            ...

    For endpoints where process_id comes from a submission lookup:
        # Use verify_submission_access instead
    """

    def __call__(
        self,
        process_id: str,
        auth: AuthContext = Depends(verify_api_key),
    ) -> AuthContext:
        """Check if the authenticated key can access the given process."""
        from services.api_keys import verify_key_for_process

        if not verify_key_for_process(auth.process_ids, process_id):
            logger.warning(f"Key {auth.key_id} denied access to process {process_id}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "success": False,
                    "message": f"This API key does not have access to process '{process_id}'",
                    "data": None,
                },
            )
        return auth


def verify_process_access(
    process_id: str,
    auth: AuthContext = Depends(verify_api_key),
) -> AuthContext:
    """
    Verify that the authenticated key can access a specific process.

    Args:
        process_id: The process ID to check access for
        auth: The authentication context from verify_api_key

    Returns:
        The auth context if access is allowed

    Raises:
        HTTPException 403 if access is denied
    """
    from services.api_keys import verify_key_for_process

    if not verify_key_for_process(auth.process_ids, process_id):
        logger.warning(f"Key {auth.key_id} denied access to process {process_id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "success": False,
                "message": f"This API key does not have access to process '{process_id}'",
                "data": None,
            },
        )
    return auth


def get_submission_process_id(submission_id: str, db: Session) -> Optional[str]:
    """
    Helper to look up a submission's process_id.

    Args:
        submission_id: The submission ID to look up
        db: Database session

    Returns:
        The process_id if found, None otherwise
    """
    from db.models import Submission

    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    return submission.process_id if submission else None


def get_document_process_id(document_id: str, db: Session) -> Optional[str]:
    """
    Helper to look up a document's process_id (via its submission).

    Args:
        document_id: The document ID to look up
        db: Database session

    Returns:
        The process_id if found, None otherwise
    """
    from db.models import Submission, SubmissionDocument

    document = (
        db.query(SubmissionDocument)
        .filter(SubmissionDocument.id == document_id)
        .first()
    )
    if not document:
        return None

    submission = (
        db.query(Submission).filter(Submission.id == document.submission_id).first()
    )
    return submission.process_id if submission else None
