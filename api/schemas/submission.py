from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime


# Request schemas

class SubmissionCreate(BaseModel):
    process_id: str = Field(
        ...,
        description="The process this submission belongs to",
        examples=["proc_a1b2c3d4e5f6"],
    )
    reference: Optional[str] = Field(
        default=None,
        max_length=200,
        description="Your internal case reference number",
        examples=["APP-2025-001"],
    )
    applicant_id: Optional[str] = Field(
        default=None,
        max_length=200,
        description="Your system's applicant / user ID",
        examples=["usr_emeka_obi"],
    )

    class Config:
        json_schema_extra = {
            "example": {
                "process_id": "proc_a1b2c3d4e5f6",
                "reference": "APP-2025-001",
                "applicant_id": "usr_emeka_obi",
            }
        }


# Response schemas

class SubmissionProgress(BaseModel):
    classified: int = Field(description="Documents successfully classified")
    required: int = Field(description="Total documents required by process")

    class Config:
        json_schema_extra = {
            "example": {"classified": 5, "required": 22}
        }


class SubmissionOut(BaseModel):
    submission_id: str
    process_id: str
    reference: Optional[str]
    applicant_id: Optional[str]
    status: str
    progress: SubmissionProgress
    documents_uploaded: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "submission_id": "sub_k9m2xp12",
                "process_id": "proc_a1b2c3d4e5f6",
                "reference": "APP-2025-001",
                "applicant_id": "usr_emeka_obi",
                "status": "in_progress",
                "progress": {"classified": 5, "required": 22},
                "documents_uploaded": 5,
                "created_at": "2025-05-20T10:15:00",
                "updated_at": "2025-05-20T11:30:00",
            }
        }


class SubmissionListData(BaseModel):
    items: List[SubmissionOut]
    total: int
