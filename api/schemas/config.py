from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


# ── Request schemas ────────────────────────────────────────────────────────
class RuleUpdate(BaseModel):
    """
    Partial update — send only the fields you want to change.
    Both fields are optional so you can update one at a time.
    """

    enabled: Optional[bool] = Field(
        default=None,
        description="Enable or disable this rule",
        examples=[False],
    )
    severity: Optional[str] = Field(
        default=None,
        description="error | warning",
        examples=["warning"],
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "enabled": False,
                "severity": "warning",
            }
        }
    }


class ThresholdUpdate(BaseModel):
    """
    Update the confidence thresholds that control routing decisions.
    auto_above must be greater than manual_below.
    """

    auto_above: int = Field(
        ...,
        ge=51,
        le=99,
        description=(
            "Fields at or above this confidence are auto-processed. "
            "Must be between 51 and 99."
        ),
        examples=[85],
    )
    manual_below: int = Field(
        ...,
        ge=1,
        le=79,
        description=(
            "Fields below this confidence require manual input. "
            "Must be between 1 and 79."
        ),
        examples=[60],
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "auto_above": 85,
                "manual_below": 60,
            }
        }
    }


class ValidationRuleCreate(BaseModel):
    name: str = Field(..., min_length=3, max_length=200)
    rule_type: str = Field(..., pattern="^(required|format|logical|cross_doc)$")
    field: str = Field(..., min_length=1, max_length=100)
    severity: str = Field(default="error", pattern="^(error|warning)$")
    pattern: Optional[str] = Field(default=None, max_length=500)
    check: Optional[str] = Field(default=None, max_length=100)


# ── Response schemas ───────────────────────────────────────────────────────
class RuleOut(BaseModel):
    id: str
    name: str
    rule_type: str
    field: str
    check: Optional[str]
    pattern: Optional[str]
    severity: str
    is_enabled: bool
    created_at: datetime

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "id": "rule_r01a2b3c4d5e",
                "name": "Full name required",
                "rule_type": "required",
                "field": "Full Name",
                "check": None,
                "pattern": None,
                "severity": "error",
                "is_enabled": True,
                "created_at": "2025-05-20T10:00:00",
            }
        },
    }


class RuleListData(BaseModel):
    items: List[RuleOut]
    total: int
    enabled: int
    disabled: int
