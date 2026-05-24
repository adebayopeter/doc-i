from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel

# Generic type for the data payload
T = TypeVar("T")


class APIResponse(BaseModel, Generic[T]):
    """
    Standard response envelope for every endpoint.

    Every response in this API follows this structure:
    {
        "success": true,
        "message": "Request successful",
        "data": { ... }
    }

    On error:
    {
        "success": false,
        "message": "Process not found",
        "data": null
    }
    """

    success: bool
    message: str
    data: Optional[T] = None

    model_config = {
        "populate_by_name": True,
        "json_schema_extra": {
            "example": {"success": True, "message": "Request successful", "data": {}}
        },
    }


class PaginatedResponse(BaseModel, Generic[T]):
    """
    Standard envelope for list endpoints that return multiple items.

    {
        "success": true,
        "message": "Request successful",
        "data": {
            "items": [...],
            "total": 10,
            "page": 1,
            "per_page": 20
        }
    }
    """

    success: bool
    message: str
    data: Optional[T] = None


# Helpers: call these in every router
def success_response(
    data: Any = None,
    message: str = "Request successful",
) -> dict:
    """
    Returns a standard success response dict.

    Usage in any router:
        return success_response(
            data={"process_id": "proc_abc123"},
            message="Process created successfully"
        )
    """
    return {
        "success": True,
        "message": message,
        "data": data,
    }


def error_response(
    message: str,
    data: Any = None,
) -> dict:
    """
    Returns a standard error response dict.
    Use this inside HTTPException detail — not directly as a return.

    Usage:
        raise HTTPException(
            status_code=404,
            detail=error_response("Process not found")
        )
    """
    return {
        "success": False,
        "message": message,
        "data": data,
    }
