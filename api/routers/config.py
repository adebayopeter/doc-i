"""
Config router — /v1/config

Manages platform-wide configuration — validation rules and
confidence thresholds. Changes take effect immediately on all
subsequent analysis requests. No redeploy required.

Endpoints:
    GET    /v1/config/rules              List all validation rules
    GET    /v1/config/rules/{rule_id}    Get a single rule
    PATCH  /v1/config/rules/{rule_id}    Enable, disable or adjust a rule
    GET    /v1/config/thresholds         Get current confidence thresholds
    PUT    /v1/config/thresholds         Update confidence thresholds
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from config.dependencies import get_db, verify_api_key
from config.logging import get_logger
from db.models import ValidationRule
from schemas.base import error_response, success_response
from schemas.config import (
    ProcessThresholdUpdate,
    RuleUpdate,
    ThresholdUpdate,
    ValidationRuleCreate,
)
from services.decisioning import DEFAULT_THRESHOLDS

logger = get_logger(__name__)

# ── Module-level dependencies ──────────────────────────────────────────────
db_dependency = Depends(get_db)
auth_dependency = Depends(verify_api_key)

# ── Threshold helpers ──────────────────────────────────────────────────────
_GLOBAL_THRESHOLD_FALLBACK = dict(DEFAULT_THRESHOLDS)


def get_current_thresholds(db=None) -> dict:
    """
    Returns the global threshold dict.
    If db is provided, reads from DB. Otherwise uses in-memory fallback.
    Called at request time from analysis router.
    """
    if db is None:
        return _GLOBAL_THRESHOLD_FALLBACK

    from db.models import ProcessThreshold

    global_row = (
        db.query(ProcessThreshold).filter(ProcessThreshold.process_id.is_(None)).first()
    )
    if global_row:
        return {
            "autoAbove": global_row.auto_above,
            "manualBelow": global_row.manual_below,
        }
    return _GLOBAL_THRESHOLD_FALLBACK


def get_process_thresholds(process_id: str, db) -> dict:
    """
    Returns thresholds for a specific process.
    Falls back to global if no process-specific threshold is set.
    """
    from db.models import ProcessThreshold

    # Try process-specific first
    process_row = (
        db.query(ProcessThreshold)
        .filter(ProcessThreshold.process_id == process_id)
        .first()
    )
    if process_row:
        return {
            "autoAbove": process_row.auto_above,
            "manualBelow": process_row.manual_below,
        }

    # Fall back to global
    return get_current_thresholds(db)


def _ensure_global_threshold(db) -> "ProcessThreshold":
    """Get or create the global threshold row."""
    from db.models import ProcessThreshold

    row = (
        db.query(ProcessThreshold).filter(ProcessThreshold.process_id.is_(None)).first()
    )
    if not row:
        row = ProcessThreshold(
            process_id=None,
            auto_above=DEFAULT_THRESHOLDS["autoAbove"],
            manual_below=DEFAULT_THRESHOLDS["manualBelow"],
        )
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


# ── Shared response examples ───────────────────────────────────────────────
_401 = {
    "description": "Unauthorised — missing or invalid API key",
    "content": {
        "application/json": {
            "example": {
                "success": False,
                "message": "Invalid API key",
                "data": None,
            }
        }
    },
}

_404_rule = {
    "description": "Rule not found",
    "content": {
        "application/json": {
            "example": {
                "success": False,
                "message": "Validation rule not found",
                "data": None,
            }
        }
    },
}

_500 = {
    "description": "Internal server error",
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

router = APIRouter(
    dependencies=[auth_dependency],
    responses={401: _401, 500: _500},
)


# ── Helpers ────────────────────────────────────────────────────────────────
def _get_rule_or_404(rule_id: str, db: Session) -> ValidationRule:
    """Fetch a validation rule by ID. Raises 404 if not found."""
    rule = db.query(ValidationRule).filter(ValidationRule.id == rule_id).first()
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_response("Validation rule not found"),
        )
    return rule


def _build_rule_out(rule: ValidationRule) -> dict:
    """Build a rule response dict from a ValidationRule ORM object."""
    return {
        "id": rule.id,
        "name": rule.name,
        "rule_type": rule.rule_type,
        "field": rule.field,
        "check": rule.check,
        "pattern": rule.pattern,
        "severity": rule.severity,
        "is_enabled": rule.is_enabled,
        "process_id": rule.process_id,
        "scope": "global" if rule.process_id is None else "process",
        "created_at": (rule.created_at.isoformat() if rule.created_at else None),
    }


# ── GET /v1/config/rules ──────────────────────────────────────────────────
@router.get(
    "/rules",
    summary="List all validation rules",
    description=(
        "Returns validation rules with their current enabled state.\n\n"
        "**Filtering:**\n"
        "- `?scope=global` — only global rules (no process_id)\n"
        "- `?scope=process` — only process-scoped rules\n"
        "- `?process_id=proc_xxx` — rules for a specific process "
        "(includes both global rules and rules scoped to that process)\n\n"
        "**Rule types:**\n"
        "- `required` — field must be present and non-null\n"
        "- `format` — value must match a regex pattern\n"
        "- `logical` — date/age/expiry check\n"
        "- `cross_doc` — value must be consistent across documents\n\n"
        "**Scope:**\n"
        "- `global` — runs on every process (process_id is null)\n"
        "- `process` — runs only for the specific process it is tied to"
    ),
    response_description="Rules retrieved successfully",
    responses={
        200: {
            "description": "Rules retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "message": "Validation rules retrieved successfully",
                        "data": {
                            "items": [
                                {
                                    "id": "rule_r01a2b3c4d5e",
                                    "name": "Full name required",
                                    "rule_type": "required",
                                    "field": "Full Name",
                                    "check": None,
                                    "pattern": None,
                                    "severity": "error",
                                    "is_enabled": True,
                                    "created_at": "2025-05-20T10:00:00Z",
                                },
                                {
                                    "id": "rule_r09a2b3c4d5e",
                                    "name": "NIN format (11 digits)",
                                    "rule_type": "format",
                                    "field": "NIN",
                                    "check": None,
                                    "pattern": r"^\d{11}$",
                                    "severity": "error",
                                    "is_enabled": True,
                                    "created_at": "2025-05-20T10:00:00Z",
                                },
                                {
                                    "id": "rule_r04a2b3c4d5e",
                                    "name": "Applicant aged 18 or over",
                                    "rule_type": "logical",
                                    "field": "Date of Birth",
                                    "check": "min_age_18",
                                    "pattern": None,
                                    "severity": "error",
                                    "is_enabled": True,
                                    "created_at": "2025-05-20T10:00:00Z",
                                },
                            ],
                            "total": 12,
                            "enabled": 11,
                            "disabled": 1,
                            "global_count": 10,
                            "process_count": 2,
                        },
                    }
                }
            },
        },
    },
)
def list_rules(
    process_id: Optional[str] = None,
    scope: Optional[str] = None,
    db: Session = db_dependency,
):
    from sqlalchemy import or_

    query = db.query(ValidationRule)

    if process_id:
        # Return global rules + rules scoped to this process
        query = query.filter(
            or_(
                ValidationRule.process_id.is_(None),
                ValidationRule.process_id == process_id,
            )
        )
    elif scope == "global":
        query = query.filter(ValidationRule.process_id.is_(None))
    elif scope == "process":
        query = query.filter(ValidationRule.process_id.isnot(None))

    rules = query.order_by(ValidationRule.created_at.asc()).all()
    enabled = len([r for r in rules if r.is_enabled])
    global_count = len([r for r in rules if r.process_id is None])
    process_count = len([r for r in rules if r.process_id is not None])

    logger.info(
        f"Listed {len(rules)} rules "
        f"(global={global_count} process={process_count} enabled={enabled})"
    )

    return success_response(
        data={
            "items": [_build_rule_out(r) for r in rules],
            "total": len(rules),
            "enabled": enabled,
            "disabled": len(rules) - enabled,
            "global_count": global_count,
            "process_count": process_count,
        },
        message="Validation rules retrieved successfully",
    )


@router.post(
    "/rules",
    status_code=status.HTTP_201_CREATED,
    summary="Create a validation rule",
    responses={
        201: {
            "description": "Rule created",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "message": "Validation rule created successfully",
                        "data": {
                            "id": "rule_abc123def456",
                            "name": "Passport not expired",
                            "rule_type": "logical",
                            "field": "Expiry Date",
                            "check": "not_expired",
                            "pattern": None,
                            "severity": "error",
                            "is_enabled": True,
                            "created_at": "2025-05-20T10:00:00",
                        },
                    }
                }
            },
        },
    },
)
def create_rule(
    payload: ValidationRuleCreate,
    db: Session = db_dependency,
):
    from sqlalchemy import or_

    # Check for duplicate name within same scope
    query = db.query(ValidationRule).filter(ValidationRule.name.ilike(payload.name))
    if payload.process_id:
        query = query.filter(
            or_(
                ValidationRule.process_id == payload.process_id,
                ValidationRule.process_id.is_(None),
            )
        )
    existing = query.first()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=error_response(
                f"A rule named '{payload.name}' already exists",
                data={"existing_id": existing.id},
            ),
        )

    # Validate process exists if process_id provided
    if payload.process_id:
        from db.models import Process

        process = (
            db.query(Process)
            .filter(
                Process.id == payload.process_id,
                Process.is_active.is_(True),
            )
            .first()
        )
        if not process:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_response(f"Process '{payload.process_id}' not found"),
            )

    rule = ValidationRule(
        name=payload.name,
        rule_type=payload.rule_type,
        field=payload.field,
        severity=payload.severity,
        pattern=payload.pattern,
        check=payload.check,
        process_id=payload.process_id,
        is_enabled=True,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)

    scope = "global" if not payload.process_id else f"process {payload.process_id}"
    logger.info(f"Validation rule created: {rule.id} ({rule.name}) scope={scope}")

    return success_response(
        data=_build_rule_out(rule),
        message="Validation rule created successfully",
    )


# ── GET /v1/config/rules/{rule_id} ────────────────────────────────────────
@router.get(
    "/rules/{rule_id}",
    summary="Get a validation rule",
    description=(
        "Returns a single validation rule by ID including its current "
        "enabled state, type, field, and any pattern or check configured."
    ),
    response_description="Rule retrieved successfully",
    responses={
        200: {
            "description": "Rule retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "message": "Validation rule retrieved successfully",
                        "data": {
                            "id": "rule_r01a2b3c4d5e",
                            "name": "Full name required",
                            "rule_type": "required",
                            "field": "Full Name",
                            "check": None,
                            "pattern": None,
                            "severity": "error",
                            "is_enabled": True,
                            "created_at": "2025-05-20T10:00:00Z",
                        },
                    }
                }
            },
        },
        404: _404_rule,
    },
)
def get_rule(
    rule_id: str,
    db: Session = db_dependency,
):
    rule = _get_rule_or_404(rule_id, db)
    logger.info(f"Retrieved rule: {rule_id}")

    return success_response(
        data=_build_rule_out(rule),
        message="Validation rule retrieved successfully",
    )


# ── PATCH /v1/config/rules/{rule_id} ─────────────────────────────────────
@router.patch(
    "/rules/{rule_id}",
    summary="Update a validation rule",
    description=(
        "Partially updates a validation rule. "
        "Send only the fields you want to change — omit the rest.\n\n"
        "Changes take effect immediately on all subsequent "
        "validation requests. No redeploy required.\n\n"
        "**What you can change:**\n"
        "- `enabled` — toggle the rule on or off\n"
        "- `severity` — change between `error` and `warning`\n\n"
        "Rule type, field, check, and pattern are fixed at creation "
        "and cannot be changed."
    ),
    response_description="Rule updated successfully",
    responses={
        200: {
            "description": "Rule updated successfully",
            "content": {
                "application/json": {
                    "examples": {
                        "disable_rule": {
                            "summary": "Disable a rule",
                            "value": {
                                "success": True,
                                "message": "Validation rule updated successfully",
                                "data": {
                                    "id": "rule_r01a2b3c4d5e",
                                    "name": "Full name required",
                                    "rule_type": "required",
                                    "field": "Full Name",
                                    "check": None,
                                    "pattern": None,
                                    "severity": "error",
                                    "is_enabled": False,
                                    "created_at": "2025-05-20T10:00:00Z",
                                },
                            },
                        },
                        "change_severity": {
                            "summary": "Downgrade to warning",
                            "value": {
                                "success": True,
                                "message": "Validation rule updated successfully",
                                "data": {
                                    "id": "rule_r05a2b3c4d5e",
                                    "name": "Applicant under 75",
                                    "rule_type": "logical",
                                    "field": "Date of Birth",
                                    "check": "max_age_75",
                                    "pattern": None,
                                    "severity": "warning",
                                    "is_enabled": True,
                                    "created_at": "2025-05-20T10:00:00Z",
                                },
                            },
                        },
                    }
                }
            },
        },
        404: _404_rule,
        422: {
            "description": "Invalid severity value",
            "content": {
                "application/json": {
                    "example": {
                        "success": False,
                        "message": (
                            "Invalid severity 'critical'. "
                            "Must be one of: error, warning"
                        ),
                        "data": None,
                    }
                }
            },
        },
    },
)
def update_rule(
    rule_id: str,
    payload: RuleUpdate,
    db: Session = db_dependency,
):
    rule = _get_rule_or_404(rule_id, db)

    # Validate severity if provided
    if payload.severity is not None:
        if payload.severity not in {"error", "warning"}:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=error_response(
                    f"Invalid severity '{payload.severity}'. "
                    f"Must be one of: error, warning"
                ),
            )
        rule.severity = payload.severity

    if payload.enabled is not None:
        rule.is_enabled = payload.enabled

    db.commit()
    db.refresh(rule)

    logger.info(
        f"Rule updated: {rule_id} "
        f"enabled={rule.is_enabled} severity={rule.severity}"
    )

    return success_response(
        data=_build_rule_out(rule),
        message="Validation rule updated successfully",
    )


# ── GET /v1/config/thresholds ─────────────────────────────────────────────
@router.get(
    "/thresholds",
    summary="Get global confidence thresholds",
    description=(
        "Returns the **global default** confidence thresholds used for "
        "routing decisions. These apply to all processes unless a process "
        "has its own threshold configured.\n\n"
        "To get thresholds for a specific process (which may override these), "
        "use `GET /v1/processes/{id}/thresholds`.\n\n"
        "- Fields with confidence ≥ `auto_above` → **auto-process**\n"
        "- Fields between `manual_below` and `auto_above` → **review**\n"
        "- Fields with confidence < `manual_below` → **manual input**"
    ),
    response_description="Thresholds retrieved successfully",
    responses={
        200: {
            "description": "Global thresholds retrieved",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "message": "Thresholds retrieved successfully",
                        "data": {
                            "auto_above": 85,
                            "manual_below": 60,
                            "scope": "global",
                            "process_id": None,
                            "is_override": False,
                            "description": {
                                "auto": "confidence ≥ 85% → auto-process",
                                "review": "60% ≤ confidence < 85% → review",
                                "manual": "confidence < 60% → manual input",
                            },
                        },
                    }
                }
            },
        },
    },
)
def get_thresholds(db: Session = db_dependency):
    row = _ensure_global_threshold(db)
    auto_above = row.auto_above
    manual_below = row.manual_below

    # Keep in-memory fallback in sync
    _GLOBAL_THRESHOLD_FALLBACK["autoAbove"] = auto_above
    _GLOBAL_THRESHOLD_FALLBACK["manualBelow"] = manual_below

    return success_response(
        data={
            "auto_above": auto_above,
            "manual_below": manual_below,
            "scope": "global",
            "process_id": None,
            "is_override": False,
            "description": {
                "auto": f"confidence ≥ {auto_above}% → auto-process",
                "review": (f"{manual_below}% ≤ confidence < {auto_above}% → review"),
                "manual": f"confidence < {manual_below}% → manual input",
            },
        },
        message="Thresholds retrieved successfully",
    )


# ── PUT /v1/config/thresholds ─────────────────────────────────────────────
@router.put(
    "/thresholds",
    summary="Update global confidence thresholds",
    description=(
        "Updates the **global default** confidence thresholds. "
        "Changes take effect immediately for all processes that do not "
        "have their own threshold override.\n\n"
        "To set thresholds for a specific process, use "
        "`PUT /v1/processes/{id}/thresholds`.\n\n"
        "`auto_above` must be greater than `manual_below`."
    ),
    response_description="Thresholds updated successfully",
    responses={
        200: {
            "description": "Global thresholds updated",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "message": "Thresholds updated successfully",
                        "data": {
                            "auto_above": 90,
                            "manual_below": 65,
                            "scope": "global",
                            "previous": {
                                "auto_above": 85,
                                "manual_below": 60,
                            },
                        },
                    }
                }
            },
        },
        422: {
            "description": "Invalid threshold values",
            "content": {
                "application/json": {
                    "example": {
                        "success": False,
                        "message": "auto_above (60) must be greater than manual_below (60)",
                        "data": None,
                    }
                }
            },
        },
    },
)
def update_thresholds(
    payload: ThresholdUpdate,
    db: Session = db_dependency,
):
    if payload.auto_above <= payload.manual_below:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=error_response(
                f"auto_above ({payload.auto_above}) must be greater than "
                f"manual_below ({payload.manual_below})"
            ),
        )

    row = _ensure_global_threshold(db)
    previous = {
        "auto_above": row.auto_above,
        "manual_below": row.manual_below,
    }

    row.auto_above = payload.auto_above
    row.manual_below = payload.manual_below
    db.commit()
    db.refresh(row)

    # Keep in-memory fallback in sync
    _GLOBAL_THRESHOLD_FALLBACK["autoAbove"] = payload.auto_above
    _GLOBAL_THRESHOLD_FALLBACK["manualBelow"] = payload.manual_below

    logger.info(
        f"Global thresholds updated: "
        f"auto_above={payload.auto_above} "
        f"manual_below={payload.manual_below}"
    )

    return success_response(
        data={
            "auto_above": payload.auto_above,
            "manual_below": payload.manual_below,
            "scope": "global",
            "process_id": None,
            "is_override": False,
            "previous": previous,
            "description": {
                "auto": f"confidence ≥ {payload.auto_above}% → auto-process",
                "review": (
                    f"{payload.manual_below}% ≤ confidence "
                    f"< {payload.auto_above}% → review"
                ),
                "manual": f"confidence < {payload.manual_below}% → manual input",
            },
        },
        message="Thresholds updated successfully",
    )
