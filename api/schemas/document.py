from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Any
from datetime import datetime


class ExtractedField(BaseModel):
    value: Optional[str]
    confidence: float = Field(ge=0, le=100)

    class Config:
        json_schema_extra = {
            "example": {"value": "Emeka Obi", "confidence": 94.5}
        }


class DocumentFlag(BaseModel):
    type: str = Field(description="ok | warn | err")
    message: str

    class Config:
        json_schema_extra = {
            "example": {"type": "ok", "message": "Document valid and not expired"}
        }


class DocumentOut(BaseModel):
    document_id: str
    submission_id: str
    filename: str
    mime_type: Optional[str]
    status: str
    document_type: Optional[str]
    matched_doc_id: Optional[int]
    overall_confidence: Optional[float]
    extracted_fields: Optional[Dict[str, ExtractedField]]
    flags: Optional[List[DocumentFlag]]
    summary: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "document_id": "doc_r7tn4q12",
                "submission_id": "sub_k9m2xp12",
                "filename": "nin_slip.pdf",
                "mime_type": "application/pdf",
                "status": "classified",
                "document_type": "National ID / NIN slip",
                "matched_doc_id": 1,
                "overall_confidence": 91.5,
                "extracted_fields": {
                    "Full Name": {"value": "Emeka Obi", "confidence": 94},
                    "NIN": {"value": "12345678901", "confidence": 97},
                    "Date of Birth": {"value": "1990-03-15", "confidence": 89},
                    "Address": {
                        "value": "12 Adeola Odeku Street, Victoria Island, Lagos",
                        "confidence": 82,
                    },
                },
                "flags": [
                    {"type": "ok", "message": "Document valid and not expired"}
                ],
                "summary": "Valid NIN slip issued by NIMC. All fields clearly legible.",
                "created_at": "2025-05-20T10:20:00",
                "updated_at": "2025-05-20T10:20:45",
            }
        }


class DocumentUploadOut(BaseModel):
    """Immediate response after upload — before classification completes."""
    document_id: str
    submission_id: str
    filename: str
    status: str

    class Config:
        json_schema_extra = {
            "example": {
                "document_id": "doc_r7tn4q12",
                "submission_id": "sub_k9m2xp12",
                "filename": "nin_slip.pdf",
                "status": "processing",
            }
        }


class DocumentListData(BaseModel):
    items: List[DocumentOut]
    total: int
