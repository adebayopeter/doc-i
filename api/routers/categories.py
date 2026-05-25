"""
Document Category router.

    POST   /v1/config/categories         Create a new category
    GET    /v1/config/categories         List all active categories
    GET    /v1/config/categories/{id}    Get a single category
    PATCH  /v1/config/categories/{id}    Update name or description
    DELETE /v1/config/categories/{id}    Soft delete (is_active=False)
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from config.dependencies import get_db, verify_api_key
from config.logging import get_logger
from db.models import DocumentCategory
from schemas.base import error_response, success_response
from schemas.category import CategoryCreate, CategoryUpdate

logger = get_logger(__name__)

# ── Module-level dependencies (avoids B008) ────────────────────────────────
db_dependency = Depends(get_db)
auth_dependency = Depends(verify_api_key)

# ── Shared response dicts ──────────────────────────────────────────────────
_401 = {
    "description": "Missing or invalid API key",
    "content": {
        "application/json": {
            "example": {
                "success": False,
                "message": "Invalid or missing API key",
                "data": None,
            }
        }
    },
}
_404 = {
    "description": "Category not found",
    "content": {
        "application/json": {
            "example": {
                "success": False,
                "message": "Category not found",
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
                "message": "Name already exists",
                "data": None,
            }
        }
    },
}
_500 = {
    "description": "Unexpected server error",
    "content": {
        "application/json": {
            "example": {
                "success": False,
                "message": "An unexpected error occurred",
                "data": None,
            }
        }
    },
}

router = APIRouter(dependencies=[auth_dependency], responses={401: _401, 500: _500})


# ── Helpers ────────────────────────────────────────────────────────────────
def _get_category_or_404(category_id: str, db: Session) -> DocumentCategory:
    """Fetch a category by ID. Raises 404 if not found or inactive."""
    category = (
        db.query(DocumentCategory).filter(DocumentCategory.id == category_id).first()
    )
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_response("Category not found"),
        )
    return category


def _build_category_out(cat: DocumentCategory) -> dict:
    return {
        "id": cat.id,
        "name": cat.name,
        "description": cat.description,
        "is_active": cat.is_active,
        "created_at": cat.created_at.isoformat() if cat.created_at else None,
    }


# ── POST /v1/config/categories ─────────────────────────────────────────────
@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Create a document category",
    description=(
        "Creates a new document category. "
        "Category names must be unique. "
        "Categories are used in process document checklists."
    ),
    responses={
        201: {
            "description": "Category created",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "message": "Category created successfully",
                        "data": {
                            "id": "cat_1a2b3c4d5e6f",
                            "name": "Identity",
                            "description": "Government-issued identity documents",
                            "is_active": True,
                            "created_at": "2025-05-20T10:00:00",
                        },
                    }
                }
            },
        },
        422: _422,
    },
)
def create_category(
    payload: CategoryCreate,
    db: Session = db_dependency,
    _: str = auth_dependency,
):
    # Check for duplicate name (case-insensitive)
    existing = (
        db.query(DocumentCategory)
        .filter(DocumentCategory.name.ilike(payload.name))
        .first()
    )
    if existing:
        if existing.is_active:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=error_response(
                    f"Category '{payload.name}' already exists",
                    data={"existing_id": existing.id},
                ),
            )
        else:
            # Reactivate soft-deleted category
            existing.name = payload.name
            existing.description = payload.description
            existing.is_active = True
            db.commit()
            db.refresh(existing)
            logger.info(f"Category reactivated: {existing.id} ({existing.name})")
            return success_response(
                data=_build_category_out(existing),
                message="Category reactivated successfully",
            )

    category = DocumentCategory(
        name=payload.name,
        description=payload.description,
    )
    db.add(category)
    db.commit()
    db.refresh(category)

    logger.info(f"Category created: {category.id} ({category.name})")
    return success_response(
        data=_build_category_out(category),
        message="Category created successfully",
    )


# ── GET /v1/config/categories ──────────────────────────────────────────────
@router.get(
    "",
    summary="List all document categories",
    description=(
        "Returns all active document categories ordered alphabetically. "
        "Use this to populate dropdowns in process configuration."
    ),
    responses={
        200: {
            "description": "Category list",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "message": "Categories retrieved successfully",
                        "data": {
                            "items": [
                                {
                                    "id": "cat_1a2b3c4d5e6f",
                                    "name": "Financial",
                                    "description": "Bank statements and financial records",
                                    "is_active": True,
                                    "created_at": "2025-05-20T10:00:00",
                                },
                                {
                                    "id": "cat_2b3c4d5e6f7a",
                                    "name": "Identity",
                                    "description": "Government-issued identity documents",
                                    "is_active": True,
                                    "created_at": "2025-05-20T10:00:00",
                                },
                            ],
                            "total": 2,
                            "active": 2,
                        },
                    }
                }
            },
        }
    },
)
def list_categories(
    include_inactive: bool = False,
    db: Session = db_dependency,
    _: str = auth_dependency,
):
    query = db.query(DocumentCategory)
    if not include_inactive:
        query = query.filter(DocumentCategory.is_active.is_(True))
    categories = query.order_by(DocumentCategory.name.asc()).all()

    active_count = sum(1 for c in categories if c.is_active)

    logger.info(f"Listed {len(categories)} categories")
    return success_response(
        data={
            "items": [_build_category_out(c) for c in categories],
            "total": len(categories),
            "active": active_count,
        },
        message="Categories retrieved successfully",
    )


# ── GET /v1/config/categories/{id} ────────────────────────────────────────
@router.get(
    "/{category_id}",
    summary="Get a single category",
    responses={
        200: {
            "description": "Category detail",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "message": "Category retrieved successfully",
                        "data": {
                            "id": "cat_1a2b3c4d5e6f",
                            "name": "Identity",
                            "description": "Government-issued identity documents",
                            "is_active": True,
                            "created_at": "2025-05-20T10:00:00",
                        },
                    }
                }
            },
        },
        404: _404,
    },
)
def get_category(
    category_id: str,
    db: Session = db_dependency,
    _: str = auth_dependency,
):
    category = _get_category_or_404(category_id, db)
    return success_response(
        data=_build_category_out(category),
        message="Category retrieved successfully",
    )


# ── PATCH /v1/config/categories/{id} ──────────────────────────────────────
@router.patch(
    "/{category_id}",
    summary="Update a category",
    description="Update the name or description. Name must remain unique.",
    responses={
        200: {
            "description": "Category updated",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "message": "Category updated successfully",
                        "data": {
                            "id": "cat_1a2b3c4d5e6f",
                            "name": "Identity Documents",
                            "description": "Updated description",
                            "is_active": True,
                            "created_at": "2025-05-20T10:00:00",
                        },
                    }
                }
            },
        },
        404: _404,
        422: _422,
    },
)
def update_category(
    category_id: str,
    payload: CategoryUpdate,
    db: Session = db_dependency,
    _: str = auth_dependency,
):
    category = _get_category_or_404(category_id, db)

    if payload.name is not None and payload.name != category.name:
        conflict = (
            db.query(DocumentCategory)
            .filter(
                DocumentCategory.name.ilike(payload.name),
                DocumentCategory.id != category_id,
            )
            .first()
        )
        if conflict:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=error_response(
                    f"Category name '{payload.name}' is already taken"
                ),
            )
        category.name = payload.name

    if payload.description is not None:
        category.description = payload.description

    db.commit()
    db.refresh(category)

    logger.info(f"Category updated: {category.id} ({category.name})")
    return success_response(
        data=_build_category_out(category),
        message="Category updated successfully",
    )


# ── DELETE /v1/config/categories/{id} ─────────────────────────────────────
@router.delete(
    "/{category_id}",
    summary="Deactivate a category",
    description=(
        "Soft deletes a category by setting is_active=False. "
        "The category will no longer appear in dropdowns "
        "but existing processes that reference it are unaffected."
    ),
    responses={
        200: {
            "description": "Category deactivated",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "message": "Category deactivated successfully",
                        "data": {"id": "cat_1a2b3c4d5e6f", "name": "Identity"},
                    }
                }
            },
        },
        404: _404,
    },
)
def delete_category(
    category_id: str,
    db: Session = db_dependency,
    _: str = auth_dependency,
):
    category = _get_category_or_404(category_id, db)

    category.is_active = False
    db.commit()

    logger.info(f"Category deactivated: {category.id} ({category.name})")
    return success_response(
        data={"id": category.id, "name": category.name},
        message="Category deactivated successfully",
    )
