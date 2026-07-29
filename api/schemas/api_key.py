"""
Pydantic schemas for API key management.

Request/response models for the /v1/admin/keys endpoints.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class ApiKeyCreate(BaseModel):
    """
    Request body for creating a new API key.

    process_ids controls access scope:
      - Empty list [] = admin key, can access ALL processes
      - ["proc_abc", "proc_xyz"] = can only access those specific processes

    scopes controls allowed operations:
      - ["read"] = GET requests only
      - ["write"] = all HTTP methods (implies read)
      - ["read", "write"] = same as ["write"]
    """

    name: str = Field(
        ...,
        min_length=3,
        max_length=200,
        description="Human-readable name for this key",
    )
    process_ids: List[str] = Field(
        default_factory=list,
        description="Process IDs this key can access. Empty = admin (all access)",
    )
    scopes: List[str] = Field(
        default_factory=lambda: ["read", "write"],
        description='Allowed scopes: "read", "write", or both',
    )
    expires_at: Optional[datetime] = Field(
        default=None,
        description="Optional expiry timestamp. NULL = never expires",
    )

    @field_validator("scopes")
    @classmethod
    def validate_scopes(cls, v: List[str]) -> List[str]:
        valid_scopes = {"read", "write"}
        for scope in v:
            if scope not in valid_scopes:
                raise ValueError(f"Invalid scope '{scope}'. Must be 'read' or 'write'")
        if not v:
            raise ValueError("At least one scope is required")
        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "Benefits Application - Production",
                "process_ids": ["proc_a1b2c3d4e5f6"],
                "scopes": ["read", "write"],
                "expires_at": "2027-12-31T23:59:59Z",
            }
        }
    }


class ApiKeyUpdate(BaseModel):
    """
    Request body for updating an existing API key.

    All fields are optional — only provided fields are updated.
    """

    name: Optional[str] = Field(
        default=None,
        min_length=3,
        max_length=200,
        description="Human-readable name for this key",
    )
    process_ids: Optional[List[str]] = Field(
        default=None,
        description="Process IDs this key can access. Empty = admin (all access)",
    )
    scopes: Optional[List[str]] = Field(
        default=None,
        description='Allowed scopes: "read", "write", or both',
    )
    is_active: Optional[bool] = Field(
        default=None,
        description="Set to false to disable the key",
    )
    expires_at: Optional[datetime] = Field(
        default=None,
        description="Optional expiry timestamp",
    )

    @field_validator("scopes")
    @classmethod
    def validate_scopes(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is None:
            return v
        valid_scopes = {"read", "write"}
        for scope in v:
            if scope not in valid_scopes:
                raise ValueError(f"Invalid scope '{scope}'. Must be 'read' or 'write'")
        if not v:
            raise ValueError("At least one scope is required")
        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "Benefits Application - Updated",
                "process_ids": ["proc_a1b2c3d4e5f6", "proc_b2c3d4e5f6a1"],
                "is_active": True,
            }
        }
    }


class ApiKeyOut(BaseModel):
    """
    API key details returned in listings and get requests.

    NEVER includes the full key or key_hash.
    Only the key_prefix is shown for identification.
    """

    id: str = Field(..., description="Key ID (key_{12hex})")
    name: str = Field(..., description="Human-readable name")
    key_prefix: str = Field(
        ...,
        description="First 12 chars of key for identification (e.g. doci_key_a1b2)",
    )
    process_ids: List[str] = Field(
        ...,
        description="Process IDs this key can access. Empty = admin",
    )
    scopes: List[str] = Field(..., description="Allowed scopes")
    is_active: bool = Field(..., description="Whether the key is active")
    is_admin: bool = Field(
        ...,
        description="True if this is an admin key (empty process_ids)",
    )
    created_at: datetime = Field(..., description="When the key was created")
    last_used_at: Optional[datetime] = Field(
        ...,
        description="Last time this key was used (NULL if never)",
    )
    request_count: int = Field(..., description="Total number of API requests made")
    expires_at: Optional[datetime] = Field(
        ...,
        description="When the key expires (NULL = never)",
    )

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "id": "key_a1b2c3d4e5f6",
                "name": "Benefits Application - Production",
                "key_prefix": "doci_key_a1b2",
                "process_ids": ["proc_a1b2c3d4e5f6"],
                "scopes": ["read", "write"],
                "is_active": True,
                "is_admin": False,
                "created_at": "2026-07-21T10:00:00Z",
                "last_used_at": "2026-07-21T14:30:00Z",
                "request_count": 1542,
                "expires_at": "2027-12-31T23:59:59Z",
            }
        },
    }


class ApiKeyCreated(BaseModel):
    """
    Response when a new API key is created.

    This is the ONLY time the full key is shown.
    Store it securely — it cannot be retrieved again.
    """

    id: str = Field(..., description="Key ID")
    name: str = Field(..., description="Human-readable name")
    key: str = Field(
        ...,
        description="The full API key. SAVE THIS NOW — it will not be shown again!",
    )
    key_prefix: str = Field(..., description="First 12 chars for identification")
    process_ids: List[str] = Field(..., description="Process IDs this key can access")
    scopes: List[str] = Field(..., description="Allowed scopes")
    is_admin: bool = Field(..., description="True if this is an admin key")
    created_at: datetime = Field(..., description="When the key was created")
    expires_at: Optional[datetime] = Field(..., description="When the key expires")
    warning: str = Field(
        default="Store this key securely. It will not be shown again.",
        description="Security warning",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "key_a1b2c3d4e5f6",
                "name": "Benefits Application - Production",
                "key": "doci_key_a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
                "key_prefix": "doci_key_a1b2",
                "process_ids": ["proc_a1b2c3d4e5f6"],
                "scopes": ["read", "write"],
                "is_admin": False,
                "created_at": "2026-07-21T10:00:00Z",
                "expires_at": "2027-12-31T23:59:59Z",
                "warning": "Store this key securely. It will not be shown again.",
            }
        }
    }


class ApiKeyRotated(BaseModel):
    """
    Response when an API key is rotated.

    The old key is immediately invalidated.
    This is the ONLY time the new key is shown.
    """

    id: str = Field(..., description="Key ID (unchanged)")
    name: str = Field(..., description="Key name (unchanged)")
    new_key: str = Field(
        ...,
        description="The new API key. SAVE THIS NOW — it will not be shown again!",
    )
    new_key_prefix: str = Field(..., description="New key prefix for identification")
    old_key_prefix: str = Field(..., description="Previous key prefix (now invalid)")
    rotated_at: datetime = Field(..., description="When the rotation occurred")
    warning: str = Field(
        default="The old key is now invalid. Update your applications immediately.",
        description="Security warning",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "key_a1b2c3d4e5f6",
                "name": "Benefits Application - Production",
                "new_key": "doci_key_x9y8z7w6v5u4t3s2r1q0p9o8n7m6l5k4",
                "new_key_prefix": "doci_key_x9y8",
                "old_key_prefix": "doci_key_a1b2",
                "rotated_at": "2026-07-21T15:00:00Z",
                "warning": "The old key is now invalid. Update your applications immediately.",
            }
        }
    }


class ApiKeyListData(BaseModel):
    """Data payload for list API keys response."""

    items: List[ApiKeyOut] = Field(..., description="List of API keys")
    total: int = Field(..., description="Total number of keys")

    model_config = {
        "json_schema_extra": {
            "example": {
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
            }
        }
    }


class ApiKeyDeletedData(BaseModel):
    """Data payload for delete API key response."""

    id: str = Field(..., description="ID of the deleted key")
    name: str = Field(..., description="Name of the deleted key")

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "key_a1b2c3d4e5f6",
                "name": "Benefits - Production",
            }
        }
    }
