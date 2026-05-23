from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from schemas.base import APIResponse


# Request schemas
class ProcessDocumentIn(BaseModel):
    """One required document in the process checklist."""

    name: str = Field(
        ...,
        min_length=2,
        max_length=300,
        description="Document name",
        examples=["National ID / NIN slip"],
    )
    category: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Document category",
        examples=["Identity"],
    )
    is_required: bool = Field(
        default=True,
        description="Whether this document is mandatory",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "National ID / NIN slip",
                "category": "Identity",
                "is_required": True,
            }
        }
    }


class ProcessCreate(BaseModel):
    """Request body for creating a new process."""

    name: str = Field(
        ...,
        min_length=2,
        max_length=200,
        description="Process name",
        examples=["RSA Mortgage"],
    )
    description: Optional[str] = Field(
        default=None,
        max_length=1000,
        description="What this process is for",
        examples=["Residential mortgage application — 22 required documents"],
    )
    color_var: str = Field(
        default="info",
        description="UI accent colour: info | success | warning | danger",
        examples=["info"],
    )
    icon: str = Field(
        default="ti-file",
        description="Tabler icon name for the UI",
        examples=["ti-home-2"],
    )
    documents: List[ProcessDocumentIn] = Field(
        ...,
        min_length=1,
        description="List of required documents for this process",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "RSA Mortgage",
                "description": "Residential mortgage application — 22 required documents",
                "color_var": "info",
                "icon": "ti-home-2",
                "documents": [
                    {
                        "name": "National ID / NIN slip",
                        "category": "Identity",
                        "is_required": True,
                    },
                    {
                        "name": "Bank statement (6 months)",
                        "category": "Financial",
                        "is_required": True,
                    },
                    {
                        "name": "Offer letter / Employment letter",
                        "category": "Income",
                        "is_required": True,
                    },
                ],
            }
        }
    }


# ── Response schemas ───────────────────────────────────────────────────────
class ProcessDocumentOut(BaseModel):
    """One document in the process checklist — returned in responses."""

    id: int
    name: str
    category: str
    is_required: bool
    sort_order: int

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "id": 1,
                "name": "National ID / NIN slip",
                "category": "Identity",
                "is_required": True,
                "sort_order": 0,
            }
        },
    }


class ProcessSummary(BaseModel):
    """Compact process representation — used in list responses."""

    process_id: str
    name: str
    description: Optional[str]
    document_count: int
    color_var: str
    icon: str
    created_at: datetime

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "process_id": "proc_a1b2c3d4e5f6",
                "name": "RSA Mortgage",
                "description": "Residential mortgage application",
                "document_count": 22,
                "color_var": "info",
                "icon": "ti-home-2",
                "created_at": "2025-05-20T10:00:00",
            }
        },
    }


class ProcessDetail(BaseModel):
    """Full process with document checklist — used in single-item responses."""

    process_id: str
    name: str
    description: Optional[str]
    color_var: str
    icon: str
    document_count: int
    documents: List[ProcessDocumentOut]
    created_at: datetime

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "process_id": "proc_a1b2c3d4e5f6",
                "name": "RSA Mortgage",
                "description": "Residential mortgage application",
                "color_var": "info",
                "icon": "ti-home-2",
                "document_count": 3,
                "documents": [
                    {
                        "id": 1,
                        "name": "National ID / NIN slip",
                        "category": "Identity",
                        "is_required": True,
                        "sort_order": 0,
                    },
                    {
                        "id": 2,
                        "name": "Bank statement (6 months)",
                        "category": "Financial",
                        "is_required": True,
                        "sort_order": 1,
                    },
                ],
                "created_at": "2025-05-20T10:00:00",
            }
        },
    }


class ProcessListData(BaseModel):
    """Data payload for the list processes response."""

    items: List[ProcessSummary]
    total: int

    model_config = {
        "json_schema_extra": {
            "example": {
                "items": [
                    {
                        "process_id": "proc_a1b2c3d4e5f6",
                        "name": "RSA Mortgage",
                        "description": "Residential mortgage application",
                        "document_count": 22,
                        "color_var": "info",
                        "icon": "ti-home-2",
                        "created_at": "2025-05-20T10:00:00",
                    }
                ],
                "total": 1,
            }
        }
    }


class ProcessDeactivateData(BaseModel):
    process_id: str

    model_config = {
        "json_schema_extra": {"example": {"process_id": "proc_a1b2c3d4e5f6"}}
    }


# ── Typed API response wrappers ────────────────────────────────────────────
# These are what the router declares as response_model.
# FastAPI uses them to generate accurate Swagger/ReDoc documentation.


class ProcessDetailResponse(APIResponse[ProcessDetail]):
    model_config = {
        "json_schema_extra": {
            "example": {
                "success": True,
                "message": "Process created successfully",
                "data": {
                    "process_id": "proc_a1b2c3d4e5f6",
                    "name": "RSA Mortgage",
                    "description": "Residential mortgage application",
                    "color_var": "info",
                    "icon": "ti-home-2",
                    "document_count": 3,
                    "documents": [
                        {
                            "id": 1,
                            "name": "National ID / NIN slip",
                            "category": "Identity",
                            "is_required": True,
                            "sort_order": 0,
                        },
                        {
                            "id": 2,
                            "name": "Bank statement (6 months)",
                            "category": "Financial",
                            "is_required": True,
                            "sort_order": 1,
                        },
                    ],
                    "created_at": "2025-05-20T10:00:00Z",
                },
            }
        }
    }


class ProcessListResponse(APIResponse[ProcessListData]):
    model_config = {
        "json_schema_extra": {
            "example": {
                "success": True,
                "message": "Processes retrieved successfully",
                "data": {
                    "items": [
                        {
                            "process_id": "proc_a1b2c3d4e5f6",
                            "name": "RSA Mortgage",
                            "description": "Residential mortgage application",
                            "document_count": 22,
                            "color_var": "info",
                            "icon": "ti-home-2",
                            "created_at": "2025-05-20T10:00:00Z",
                        }
                    ],
                    "total": 1,
                },
            }
        }
    }


class ProcessDeactivateResponse(APIResponse[ProcessDeactivateData]):
    model_config = {
        "json_schema_extra": {
            "example": {
                "success": True,
                "message": "Process deactivated successfully",
                "data": {"process_id": "proc_a1b2c3d4e5f6"},
            }
        }
    }
