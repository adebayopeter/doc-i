from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class RuleUpdate(BaseModel):
    enabled: Optional[bool] = Field(
        default=None, description="Enable or disable this rule"
    )
    severity: Optional[str] = Field(
        default=None,
        description="error | warning",
        examples=["warning"],
    )

    class Config:
        json_schema_extra = {
            "example": {
                "enabled": False,
                "severity": "warning",
            }
        }


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

    class Config:
        from_attributes = True
        json_schema_extra = {
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
        }


class RuleListData(BaseModel):
    items: List[RuleOut]
    total: int
