"""
Schemas for per-process extraction field configuration.
"""

from typing import List, Optional

from pydantic import BaseModel, Field


class ExtractionFieldCreate(BaseModel):
    name: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Field name — must be unique within the process",
        examples=["Full Name"],
    )
    description: Optional[str] = Field(
        default=None,
        max_length=255,
        examples=["Legal full name of the applicant"],
    )
    include_in_decision: bool = Field(
        default=True,
        description="Whether this field affects the routing decision",
    )
    null_is_manual: bool = Field(
        default=False,
        description=(
            "If True, a missing or null value routes to manual. "
            "If False, missing fields are skipped in decisioning."
        ),
    )
    sort_order: int = Field(
        default=0,
        description="Display order",
    )


class ExtractionFieldUpdate(BaseModel):
    """Partial update — send only fields you want to change."""

    description: Optional[str] = Field(default=None, max_length=255)
    is_active: Optional[bool] = Field(default=None)
    include_in_decision: Optional[bool] = Field(default=None)
    null_is_manual: Optional[bool] = Field(default=None)
    sort_order: Optional[int] = Field(default=None)


class ExtractionFieldOut(BaseModel):
    id: str
    process_id: str
    name: str
    description: Optional[str]
    is_active: bool
    include_in_decision: bool
    null_is_manual: bool
    sort_order: int
    created_at: str

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "id": "pef_1a2b3c4d5e6f",
                "process_id": "proc_1a2b3c4d5e6f",
                "name": "Full Name",
                "description": "Legal full name of the applicant",
                "is_active": True,
                "include_in_decision": True,
                "null_is_manual": True,
                "sort_order": 1,
                "created_at": "2025-05-20T10:00:00",
            }
        },
    }


class ExtractionFieldListData(BaseModel):
    items: List[ExtractionFieldOut]
    total: int
    active: int
    extraction_enabled: bool
