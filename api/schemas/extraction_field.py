"""
Schemas for per-process extraction field configuration.

Fields are tied to a specific document in the process checklist (ProcessDocument),
not to the process as a whole. This means each document type declares exactly
which fields it expects — enabling precise missing-field reporting.
"""

from typing import List, Optional

from pydantic import BaseModel, Field


class DocumentFieldCreate(BaseModel):
    """Add a field to a specific document in the process checklist."""

    name: str = Field(
        ...,
        min_length=2,
        max_length=200,
        description="Field name — must be unique within this checklist document",
        examples=["Full Name"],
    )
    description: Optional[str] = Field(
        default=None,
        max_length=255,
        examples=["Legal full name as it appears on the document"],
    )
    include_in_decision: bool = Field(
        default=True,
        description=(
            "Whether this field's confidence score affects the routing "
            "decision for the submission"
        ),
    )
    null_is_manual: bool = Field(
        default=False,
        description=(
            "If True, a missing or null value for this field routes the "
            "submission to manual. Use for required fields like NIN or "
            "Account Number. If False, a missing value is skipped in "
            "decisioning."
        ),
    )
    sort_order: int = Field(
        default=0,
        ge=0,
        description="Display order within this document's field list",
    )


class DocumentFieldUpdate(BaseModel):
    """Partial update — send only the fields you want to change."""

    description: Optional[str] = Field(default=None, max_length=255)
    is_active: Optional[bool] = Field(
        default=None,
        description="Disable without deleting — disabled fields are not sent to Claude",
    )
    include_in_decision: Optional[bool] = Field(default=None)
    null_is_manual: Optional[bool] = Field(default=None)
    sort_order: Optional[int] = Field(default=None, ge=0)


class DocumentFieldOut(BaseModel):
    """Single field response."""

    id: str
    process_document_id: int
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
                "id": "pdf_1a2b3c4d5e6f",
                "process_document_id": 1,
                "name": "NIN",
                "description": "11-digit National Identification Number",
                "is_active": True,
                "include_in_decision": True,
                "null_is_manual": True,
                "sort_order": 2,
                "created_at": "2026-05-20T10:00:00+00:00",
            }
        },
    }


class DocumentFieldListData(BaseModel):
    """List of fields for one checklist document."""

    process_document_id: int
    document_name: str
    items: List[DocumentFieldOut]
    total: int
    active: int
    fields_configured: bool = Field(
        description=(
            "True if at least one active field is configured. "
            "Documents without fields will be classified but "
            "no fields will be extracted."
        )
    )


class ProcessFieldSummary(BaseModel):
    """
    Summary of field configuration across all documents in a process.
    Used to determine whether extraction is enabled for the process.
    """

    process_id: str
    total_documents: int
    documents_with_fields: int
    documents_without_fields: int
    extraction_enabled: bool = Field(
        description=(
            "True if at least one document in this process has active "
            "extraction fields configured. If False, no AI classification "
            "will run for any document uploaded to this process."
        )
    )
    documents: List[DocumentFieldListData]


class ProcessRuleCreate(BaseModel):
    """Create a validation rule scoped to a specific process."""

    name: str = Field(..., min_length=3, max_length=200)
    rule_type: str = Field(..., pattern="^(required|format|logical|cross_doc)$")
    field: str = Field(..., min_length=1, max_length=200)
    severity: str = Field(default="error", pattern="^(error|warning)$")
    pattern: Optional[str] = Field(default=None, max_length=500)
    check: Optional[str] = Field(default=None, max_length=100)
