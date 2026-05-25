"""
Schemas for document category CRUD.
"""

from typing import List, Optional

from pydantic import BaseModel, Field


class CategoryCreate(BaseModel):
    name: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Category name — must be unique",
        examples=["Identity"],
    )
    description: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Optional description of what documents belong here",
        examples=["Government-issued identity documents"],
    )


class CategoryUpdate(BaseModel):
    """Partial update — send only the fields you want to change."""

    name: Optional[str] = Field(
        default=None,
        min_length=2,
        max_length=100,
        examples=["Identity"],
    )
    description: Optional[str] = Field(
        default=None,
        max_length=255,
        examples=["Government-issued identity documents"],
    )


class CategoryOut(BaseModel):
    id: str
    name: str
    description: Optional[str]
    is_active: bool
    created_at: str

    model_config = {"from_attributes": True}

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "id": "cat_1a2b3c4d5e6f",
                "name": "Identity",
                "description": "Government-issued identity documents",
                "is_active": True,
                "created_at": "2025-05-20T10:00:00",
            }
        },
    }


class CategoryListData(BaseModel):
    items: List[CategoryOut]
    total: int
    active: int
