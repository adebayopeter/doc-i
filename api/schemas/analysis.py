from typing import Dict, List, Optional

from pydantic import BaseModel


class FieldValue(BaseModel):
    value: Optional[str]
    confidence: float
    doc_type: str
    doc_id: str
    filename: str


class UnifiedField(BaseModel):
    best_value: Optional[str]
    best_confidence: float
    source_doc_type: str
    source_doc_id: str
    has_conflict: bool
    is_null: bool
    all_values: List[FieldValue]

    class Config:
        json_schema_extra = {
            "example": {
                "best_value": "Emeka Obi",
                "best_confidence": 94,
                "source_doc_type": "National ID / NIN slip",
                "source_doc_id": "doc_r7tn4q12",
                "has_conflict": True,
                "is_null": False,
                "all_values": [
                    {
                        "value": "Emeka Obi",
                        "confidence": 94,
                        "doc_type": "National ID / NIN slip",
                        "doc_id": "doc_r7tn4q12",
                        "filename": "nin_slip.pdf",
                    },
                    {
                        "value": "E. Obi",
                        "confidence": 71,
                        "doc_type": "Bank statement",
                        "doc_id": "doc_ab12cd34",
                        "filename": "bank_stmt.pdf",
                    },
                ],
            }
        }


class UnifiedRecordData(BaseModel):
    submission_id: str
    field_count: int
    fields: Dict[str, UnifiedField]


class ValidationResult(BaseModel):
    rule_id: str
    name: str
    type: str
    field: str
    severity: str
    status: str  # pass | fail | warn | skip
    message: str

    class Config:
        json_schema_extra = {
            "example": {
                "rule_id": "rule_r08",
                "name": "Name consistent across documents",
                "type": "cross_doc",
                "field": "Full Name",
                "severity": "error",
                "status": "fail",
                "message": "Conflict: Emeka Obi vs E. Obi",
            }
        }


class ValidationSummary(BaseModel):
    passed: int
    failed: int
    warned: int
    skipped: int


class ValidationData(BaseModel):
    submission_id: str
    summary: ValidationSummary
    results: List[ValidationResult]


class FieldDecision(BaseModel):
    field: str
    value: Optional[str]
    confidence: float
    decision: str  # auto | review | manual
    has_conflict: bool
    is_missing: bool

    class Config:
        json_schema_extra = {
            "example": {
                "field": "Full Name",
                "value": "Emeka Obi",
                "confidence": 94,
                "decision": "auto",
                "has_conflict": False,
                "is_missing": False,
            }
        }


class DecisionSummary(BaseModel):
    auto: int
    review: int
    manual: int


class DecisionData(BaseModel):
    submission_id: str
    overall_decision: str  # auto | review | manual
    reason: str
    thresholds: Dict[str, int]
    summary: DecisionSummary
    field_decisions: List[FieldDecision]

    class Config:
        json_schema_extra = {
            "example": {
                "submission_id": "sub_k9m2xp12",
                "overall_decision": "review",
                "reason": "Name conflict detected across 2 documents",
                "thresholds": {"auto_above": 85, "manual_below": 60},
                "summary": {"auto": 8, "review": 2, "manual": 1},
                "field_decisions": [
                    {
                        "field": "Full Name",
                        "value": "Emeka Obi",
                        "confidence": 71,
                        "decision": "review",
                        "has_conflict": True,
                        "is_missing": False,
                    }
                ],
            }
        }
