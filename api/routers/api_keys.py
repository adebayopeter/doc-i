"""
API Keys router — /v1/admin/keys

Admin-only endpoints for managing per-process API keys.
All endpoints require admin access (master SECRET_KEY or admin key with empty process_ids).

Endpoints:
    POST   /v1/admin/keys              Create a new API key
    GET    /v1/admin/keys              List all API keys
    GET    /v1/admin/keys/{id}         Get key details
    PATCH  /v1/admin/keys/{id}         Update key settings
    POST   /v1/admin/keys/{id}/rotate  Rotate key secret
    DELETE /v1/admin/keys/{id}         Permanently revoke key
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from config.dependencies import AuthContext, get_db, require_admin
from config.logging import get_logger
from db.models import ApiKey, Process
from schemas.api_key import (
    ApiKeyCreate,
    ApiKeyCreated,
    ApiKeyDeletedData,
    ApiKeyListData,
    ApiKeyOut,
    ApiKeyRotated,
    ApiKeyUpdate,
)
from schemas.base import error_response, success_response
from services.api_keys import generate_api_key

logger = get_logger(__name__)

# ── Module-level dependencies ──────────────────────────────────────────────
db_dependency = Depends(get_db)
admin_dependency = Depends(require_admin)

# ── Shared error response examples ────────────────────────────────────────
_401 = {
    "description": "Unauthorised — missing or invalid API key",
    "content": {
        "application/json": {
            "example": {
                "success": False,
                "message": "Invalid API key",
                "data": None,
            }
        }
    },
}

_403 = {
    "description": "Forbidden — admin access required",
    "content": {
        "application/json": {
            "example": {
                "success": False,
                "message": "This endpoint requires admin access",
                "data": None,
            }
        }
    },
}

_404 = {
    "description": "API key not found",
    "content": {
        "application/json": {
            "example": {
                "success": False,
                "message": "API key not found",
                "data": None,
            }
        }
    },
}

_409 = {
    "description": "Conflict — duplicate key name",
    "content": {
        "application/json": {
            "example": {
                "success": False,
                "message": "An API key with this name already exists",
                "data": None,
            }
        }
    },
}

_422 = {
    "description": "Validation error",
    "content": {
        "application/json": {
            "example": {
                "success": False,
                "message": "Invalid process_id: proc_nonexistent",
                "data": None,
            }
        }
    },
}

router = APIRouter(
    dependencies=[admin_dependency],
    responses={
        401: _401,
        403: _403,
        404: _404,
        422: _422,
    },
)


# ── Helpers ────────────────────────────────────────────────────────────────
def _get_key_or_404(key_id: str, db: Session) -> ApiKey:
    """Fetch an API key by ID or raise 404."""
    key = db.query(ApiKey).filter(ApiKey.id == key_id).first()
    if not key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_response("API key not found"),
        )
    return key


def _validate_process_ids(process_ids: list, db: Session) -> None:
    """Validate that all process_ids exist. Raises 422 if any don't."""
    if not process_ids:
        return  # Empty list is valid (admin key)

    for pid in process_ids:
        process = (
            db.query(Process)
            .filter(Process.id == pid, Process.is_active == True)  # noqa: E712
            .first()
        )
        if not process:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=error_response(f"Invalid process_id: {pid}"),
            )


def _build_key_out(key: ApiKey) -> ApiKeyOut:
    """Build an ApiKeyOut from an ApiKey ORM object."""
    return ApiKeyOut(
        id=key.id,
        name=key.name,
        key_prefix=key.key_prefix,
        process_ids=key.process_ids or [],
        scopes=key.scopes or ["read", "write"],
        is_active=key.is_active,
        is_admin=not key.process_ids,
        created_at=key.created_at,
        last_used_at=key.last_used_at,
        request_count=key.request_count,
        expires_at=key.expires_at,
    )


# ── POST /v1/admin/keys ───────────────────────────────────────────────────
@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Create a new API key",
    description=(
        "Creates a new API key with the specified name and process scope. "
        "The full key is returned ONLY in this response — store it securely. "
        "If process_ids is empty, the key is an admin key with access to all processes."
    ),
    response_description="API key created successfully",
    responses={
        201: {
            "description": "API key created successfully",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "message": "API key created successfully",
                        "data": {
                            "id": "key_a1b2c3d4e5f6",
                            "name": "Benefits Application - Production",
                            "key": "doci_key_a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
                            "key_prefix": "doci_key_a1b2",
                            "process_ids": ["proc_a1b2c3d4e5f6"],
                            "scopes": ["read", "write"],
                            "is_admin": False,
                            "created_at": "2026-07-21T10:00:00Z",
                            "expires_at": None,
                            "warning": (
                                "Store this key securely. "
                                "It will not be shown again."
                            ),
                        },
                    }
                }
            },
        },
        409: _409,
    },
)
def create_api_key(
    payload: ApiKeyCreate,
    db: Session = db_dependency,
    auth: AuthContext = admin_dependency,
):
    """
    Create a new API key for process-scoped access.

    The full key is shown ONCE in this response. Store it securely —
    it cannot be retrieved again. Only the key_prefix is stored for
    identification.

    To create an admin key (access to all processes), pass an empty
    process_ids array.
    """
    logger.info(f"Creating API key: {payload.name}")

    # Check for duplicate name
    existing = db.query(ApiKey).filter(ApiKey.name == payload.name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=error_response(
                f"An API key named '{payload.name}' already exists",
                data={"existing_key_id": existing.id},
            ),
        )

    # Validate process_ids exist
    _validate_process_ids(payload.process_ids, db)

    # Generate the key
    full_key, key_hash, key_prefix = generate_api_key()

    # Create the database record
    api_key = ApiKey(
        name=payload.name,
        key_prefix=key_prefix,
        key_hash=key_hash,
        process_ids=payload.process_ids,
        scopes=payload.scopes,
        expires_at=payload.expires_at,
    )
    db.add(api_key)
    db.commit()
    db.refresh(api_key)

    logger.info(
        f"API key created: {api_key.id} ({api_key.name}) "
        f"scoped to {len(payload.process_ids)} processes"
    )

    return success_response(
        message="API key created successfully",
        data=ApiKeyCreated(
            id=api_key.id,
            name=api_key.name,
            key=full_key,
            key_prefix=key_prefix,
            process_ids=api_key.process_ids or [],
            scopes=api_key.scopes or ["read", "write"],
            is_admin=not api_key.process_ids,
            created_at=api_key.created_at,
            expires_at=api_key.expires_at,
        ),
    )


# ── GET /v1/admin/keys ────────────────────────────────────────────────────
@router.get(
    "",
    summary="List all API keys",
    description=(
        "Returns all API keys with their metadata. "
        "The full key and key_hash are NEVER included — only the key_prefix "
        "is shown for identification."
    ),
    response_description="List of API keys",
    responses={
        200: {
            "description": "API keys retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "message": "API keys retrieved successfully",
                        "data": {
                            "items": [
                                {
                                    "id": "key_a1b2c3d4e5f6",
                                    "name": "Benefits - Production",
                                    "key_prefix": "doci_key_a1b2",
                                    "process_ids": ["proc_a1b2c3d4e5f6"],
                                    "scopes": ["read", "write"],
                                    "is_active": True,
                                    "is_admin": False,
                                    "created_at": "2026-07-21T10:00:00Z",
                                    "last_used_at": "2026-07-21T14:30:00Z",
                                    "request_count": 1542,
                                    "expires_at": None,
                                }
                            ],
                            "total": 1,
                        },
                    }
                }
            },
        },
    },
)
def list_api_keys(
    db: Session = db_dependency,
    auth: AuthContext = admin_dependency,
):
    """
    List all API keys with usage statistics.

    Never exposes the full key or key_hash — only the prefix for identification.
    """
    keys = db.query(ApiKey).order_by(ApiKey.created_at.desc()).all()

    logger.info(f"Listed {len(keys)} API keys")

    return success_response(
        message="API keys retrieved successfully",
        data=ApiKeyListData(
            items=[_build_key_out(k) for k in keys],
            total=len(keys),
        ),
    )


# ── GET /v1/admin/keys/{key_id} ───────────────────────────────────────────
@router.get(
    "/{key_id}",
    summary="Get API key details",
    description=(
        "Returns details for a single API key including usage statistics. "
        "The full key and key_hash are NEVER included."
    ),
    response_description="API key retrieved successfully",
    responses={
        200: {
            "description": "API key retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "message": "API key retrieved successfully",
                        "data": {
                            "id": "key_a1b2c3d4e5f6",
                            "name": "Benefits - Production",
                            "key_prefix": "doci_key_a1b2",
                            "process_ids": ["proc_a1b2c3d4e5f6"],
                            "scopes": ["read", "write"],
                            "is_active": True,
                            "is_admin": False,
                            "created_at": "2026-07-21T10:00:00Z",
                            "last_used_at": "2026-07-21T14:30:00Z",
                            "request_count": 1542,
                            "expires_at": None,
                        },
                    }
                }
            },
        },
    },
)
def get_api_key(
    key_id: str,
    db: Session = db_dependency,
    auth: AuthContext = admin_dependency,
):
    """
    Get a single API key's details and usage statistics.
    """
    key = _get_key_or_404(key_id, db)

    logger.info(f"Retrieved API key: {key_id}")

    return success_response(
        message="API key retrieved successfully",
        data=_build_key_out(key),
    )


# ── PATCH /v1/admin/keys/{key_id} ─────────────────────────────────────────
@router.patch(
    "/{key_id}",
    summary="Update API key settings",
    description=(
        "Updates an API key's name, process scope, scopes, or active status. "
        "Only provided fields are updated. To rotate the key secret, use the "
        "/rotate endpoint instead."
    ),
    response_description="API key updated successfully",
    responses={
        200: {
            "description": "API key updated successfully",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "message": "API key updated successfully",
                        "data": {
                            "id": "key_a1b2c3d4e5f6",
                            "name": "Benefits - Production (Updated)",
                            "key_prefix": "doci_key_a1b2",
                            "process_ids": ["proc_a1b2c3d4e5f6", "proc_xyz"],
                            "scopes": ["read", "write"],
                            "is_active": True,
                            "is_admin": False,
                            "created_at": "2026-07-21T10:00:00Z",
                            "last_used_at": "2026-07-21T14:30:00Z",
                            "request_count": 1542,
                            "expires_at": None,
                        },
                    }
                }
            },
        },
        409: _409,
    },
)
def update_api_key(
    key_id: str,
    payload: ApiKeyUpdate,
    db: Session = db_dependency,
    auth: AuthContext = admin_dependency,
):
    """
    Update an API key's settings.

    Only provided fields are updated. To change the key secret, use
    POST /v1/admin/keys/{id}/rotate instead.
    """
    key = _get_key_or_404(key_id, db)

    # Check for name conflict if name is changing
    if payload.name and payload.name != key.name:
        conflict = (
            db.query(ApiKey)
            .filter(ApiKey.name == payload.name, ApiKey.id != key_id)
            .first()
        )
        if conflict:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=error_response(
                    f"An API key named '{payload.name}' already exists",
                    data={"existing_key_id": conflict.id},
                ),
            )
        key.name = payload.name

    # Validate and update process_ids
    if payload.process_ids is not None:
        _validate_process_ids(payload.process_ids, db)
        key.process_ids = payload.process_ids

    if payload.scopes is not None:
        key.scopes = payload.scopes

    if payload.is_active is not None:
        key.is_active = payload.is_active

    if payload.expires_at is not None:
        key.expires_at = payload.expires_at

    db.commit()
    db.refresh(key)

    logger.info(f"Updated API key: {key_id} ({key.name})")

    return success_response(
        message="API key updated successfully",
        data=_build_key_out(key),
    )


# ── POST /v1/admin/keys/{key_id}/rotate ───────────────────────────────────
@router.post(
    "/{key_id}/rotate",
    summary="Rotate API key secret",
    description=(
        "Generates a new secret for this API key and invalidates the old one. "
        "The new key is shown ONCE in this response — update your applications "
        "immediately. The old key will stop working immediately."
    ),
    response_description="API key rotated successfully",
    responses={
        200: {
            "description": "API key rotated successfully",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "message": "API key rotated successfully",
                        "data": {
                            "id": "key_a1b2c3d4e5f6",
                            "name": "Benefits - Production",
                            "new_key": "doci_key_x9y8z7w6v5u4t3s2r1q0p9o8n7m6l5k4",
                            "new_key_prefix": "doci_key_x9y8",
                            "old_key_prefix": "doci_key_a1b2",
                            "rotated_at": "2026-07-21T15:00:00Z",
                            "warning": (
                                "The old key is now invalid. "
                                "Update your applications immediately."
                            ),
                        },
                    }
                }
            },
        },
    },
)
def rotate_api_key(
    key_id: str,
    db: Session = db_dependency,
    auth: AuthContext = admin_dependency,
):
    """
    Rotate an API key's secret.

    This generates a completely new key secret and invalidates the old one.
    The new key is shown ONCE — store it securely and update your applications.
    """
    key = _get_key_or_404(key_id, db)
    old_prefix = key.key_prefix

    # Generate new key
    new_full_key, new_hash, new_prefix = generate_api_key()

    # Update the record
    key.key_prefix = new_prefix
    key.key_hash = new_hash

    db.commit()
    db.refresh(key)

    logger.info(
        f"Rotated API key: {key_id} ({key.name}) from {old_prefix} to {new_prefix}"
    )

    return success_response(
        message="API key rotated successfully",
        data=ApiKeyRotated(
            id=key.id,
            name=key.name,
            new_key=new_full_key,
            new_key_prefix=new_prefix,
            old_key_prefix=old_prefix,
            rotated_at=datetime.now(timezone.utc),
        ),
    )


# ── DELETE /v1/admin/keys/{key_id} ────────────────────────────────────────
@router.delete(
    "/{key_id}",
    summary="Permanently revoke API key",
    description=(
        "Permanently deletes an API key. This action cannot be undone. "
        "Any applications using this key will immediately lose access."
    ),
    response_description="API key deleted successfully",
    responses={
        200: {
            "description": "API key deleted successfully",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "message": "API key deleted successfully",
                        "data": {
                            "id": "key_a1b2c3d4e5f6",
                            "name": "Benefits - Production",
                        },
                    }
                }
            },
        },
    },
)
def delete_api_key(
    key_id: str,
    db: Session = db_dependency,
    auth: AuthContext = admin_dependency,
):
    """
    Permanently delete an API key.

    This immediately revokes all access for this key. The action cannot
    be undone — create a new key if needed.
    """
    key = _get_key_or_404(key_id, db)
    name = key.name

    db.delete(key)
    db.commit()

    logger.info(f"Deleted API key: {key_id} ({name})")

    return success_response(
        message="API key deleted successfully",
        data=ApiKeyDeletedData(id=key_id, name=name),
    )
