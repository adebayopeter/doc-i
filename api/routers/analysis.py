"""
Analysis router — /v1/analysis

Exposes the intelligence layer on top of classified documents.
All three endpoints operate on the complete set of classified
documents within a submission.

Endpoints:
    GET /v1/analysis/submissions/{submission_id}/record
        Unified record — merged fields from all classified documents
        with conflict detection and source traceability

    GET /v1/analysis/submissions/{submission_id}/validation.
        Validation results — all enabled rules run against
        the unified record

    GET /v1/analysis/submissions/{submission_id}/decision
        Routing decision — auto / review / manual per field
        and overall submission verdict
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from config.dependencies import get_db, verify_api_key
from config.logging import get_logger
from db.models import (
    ProcessExtractionField,
    Submission,
    SubmissionDocument,
    ValidationRule,
)
from routers.config import get_current_thresholds
from schemas.base import error_response, success_response
from services.aggregation import build_unified_record
from services.decisioning import compute_decision
from services.validation import run_rules

logger = get_logger(__name__)

# ── Module-level dependencies ──────────────────────────────────────────────
db_dependency = Depends(get_db)
auth_dependency = Depends(verify_api_key)

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

_404_submission = {
    "description": "Submission not found",
    "content": {
        "application/json": {
            "example": {
                "success": False,
                "message": "Submission not found",
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


def _get_submission_or_404(submission_id: str, db: Session) -> Submission:
    """Fetch a submission by ID. Raises 404 if not found."""
    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if not submission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_response("Submission not found"),
        )
    return submission


def _get_classified_documents(submission_id: str, db: Session) -> list:
    """
    Returns all classified documents for a submission.
    Only classified documents contribute to the unified record —
    uploaded/processing/failed documents are excluded.
    """
    return (
        db.query(SubmissionDocument)
        .filter(
            SubmissionDocument.submission_id == submission_id,
            SubmissionDocument.status == "classified",
        )
        .order_by(SubmissionDocument.created_at.asc())
        .all()
    )


# ── GET /v1/analysis/submissions/{submission_id}/record ───────────────────
@router.get(
    "/submissions/{submission_id}/record",
    summary="Get unified record",
    description=(
        "Merges extracted fields from all classified documents in a submission "
        "into a single unified record. \n\n"
        "For each field:\n"
        "- The value with the **highest confidence** is selected as `bestValue`\n"
        "- If the same field appears with **different values** across documents, "
        "`hasConflict` is set to `true`\n"
        "- All contributing source documents are tracked in `allValues`\n\n"
        "Only documents with status `classified` contribute to the record. "
        "Documents still processing are excluded."
    ),
    response_description="Unified record retrieved successfully",
    responses={
        200: {
            "description": "Unified record retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "message": "Unified record retrieved successfully",
                        "data": {
                            "submission_id": "sub_k9m2xp12",
                            "classified_document_count": 3,
                            "field_count": 8,
                            "fields": {
                                "Full Name": {
                                    "bestValue": "Emeka Obi",
                                    "bestConfidence": 94,
                                    "sourceDocType": "National ID / NIN slip",
                                    "sourceDocId": "doc_r7tn4q12",
                                    "hasConflict": True,
                                    "isNull": False,
                                    "allValues": [
                                        {
                                            "value": "Emeka Obi",
                                            "confidence": 94,
                                            "docType": "National ID / NIN slip",
                                            "docId": "doc_r7tn4q12",
                                            "filename": "nin_slip.pdf",
                                        },
                                        {
                                            "value": "E. Obi",
                                            "confidence": 71,
                                            "docType": "Bank statement",
                                            "docId": "doc_s8uv5r23",
                                            "filename": "bank_stmt.pdf",
                                        },
                                    ],
                                },
                                "NIN": {
                                    "bestValue": "12345678901",
                                    "bestConfidence": 97,
                                    "sourceDocType": "National ID / NIN slip",
                                    "sourceDocId": "doc_r7tn4q12",
                                    "hasConflict": False,
                                    "isNull": False,
                                    "allValues": [
                                        {
                                            "value": "12345678901",
                                            "confidence": 97,
                                            "docType": "National ID / NIN slip",
                                            "docId": "doc_r7tn4q12",
                                            "filename": "nin_slip.pdf",
                                        }
                                    ],
                                },
                                "Date of Birth": {
                                    "bestValue": "1990-03-15",
                                    "bestConfidence": 89,
                                    "sourceDocType": "National ID / NIN slip",
                                    "sourceDocId": "doc_r7tn4q12",
                                    "hasConflict": False,
                                    "isNull": False,
                                    "allValues": [
                                        {
                                            "value": "1990-03-15",
                                            "confidence": 89,
                                            "docType": "National ID / NIN slip",
                                            "docId": "doc_r7tn4q12",
                                            "filename": "nin_slip.pdf",
                                        }
                                    ],
                                },
                            },
                        },
                    }
                }
            },
        },
        404: _404_submission,
    },
)
def get_unified_record(
    submission_id: str,
    db: Session = db_dependency,
):
    _get_submission_or_404(submission_id, db)
    classified = _get_classified_documents(submission_id, db)
    record = build_unified_record(classified)

    logger.info(
        f"Unified record: submission={submission_id} "
        f"docs={len(classified)} fields={len(record)}"
    )

    return success_response(
        data={
            "submission_id": submission_id,
            "classified_document_count": len(classified),
            "field_count": len(record),
            "fields": record,
        },
        message="Unified record retrieved successfully",
    )


# ── GET /v1/analysis/submissions/{submission_id}/validation ───────────────
@router.get(
    "/submissions/{submission_id}/validation",
    summary="Run validation",
    description=(
        "Runs all enabled validation rules against the unified record "
        "for a submission. \n\n"
        "**Rule types:**\n"
        "- `required` — field must be present and non-null\n"
        "- `format` — field value must match a regex pattern "
        "(e.g. NIN must be 11 digits)\n"
        "- `logical` — date/age/expiry checks "
        "(e.g. applicant must be 18+, document must not be expired)\n"
        "- `cross_doc` — value must be consistent across all source documents\n\n"
        "Rules are configurable via `PUT /v1/config/rules/{rule_id}`. "
        "Disabled rules return status `skip` and do not affect the summary."
    ),
    response_description="Validation results retrieved successfully",
    responses={
        200: {
            "description": "Validation completed successfully",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "message": "Validation completed successfully",
                        "data": {
                            "submission_id": "sub_k9m2xp12",
                            "summary": {
                                "pass": 8,
                                "fail": 2,
                                "warn": 1,
                                "skip": 1,
                            },
                            "results": [
                                {
                                    "ruleId": "rule_r01",
                                    "name": "Full name required",
                                    "type": "required",
                                    "field": "Full Name",
                                    "severity": "error",
                                    "status": "pass",
                                    "message": 'Full Name present — "Emeka Obi"',
                                },
                                {
                                    "ruleId": "rule_r09",
                                    "name": "NIN format (11 digits)",
                                    "type": "format",
                                    "field": "NIN",
                                    "severity": "error",
                                    "status": "pass",
                                    "message": 'Format valid: "12345678901"',
                                },
                                {
                                    "ruleId": "rule_r08",
                                    "name": "Name consistent across documents",
                                    "type": "cross_doc",
                                    "field": "Full Name",
                                    "severity": "error",
                                    "status": "fail",
                                    "message": (
                                        'Conflicting values: "Emeka Obi" vs "E. Obi"'
                                    ),
                                },
                                {
                                    "ruleId": "rule_r05",
                                    "name": "Applicant under 75",
                                    "type": "logical",
                                    "field": "Date of Birth",
                                    "severity": "warning",
                                    "status": "pass",
                                    "message": "Applicant age: 35 years",
                                },
                            ],
                        },
                    }
                }
            },
        },
        404: _404_submission,
    },
)
def get_validation(
    submission_id: str,
    db: Session = db_dependency,
):
    _get_submission_or_404(submission_id, db)
    classified = _get_classified_documents(submission_id, db)
    record = build_unified_record(classified)
    rules = db.query(ValidationRule).all()
    results = run_rules(record, rules)

    summary = {
        "pass": len([r for r in results if r["status"] == "pass"]),
        "fail": len([r for r in results if r["status"] == "fail"]),
        "warn": len([r for r in results if r["status"] == "warn"]),
        "skip": len([r for r in results if r["status"] == "skip"]),
    }

    logger.info(
        f"Validation: submission={submission_id} "
        f"pass={summary['pass']} fail={summary['fail']} "
        f"warn={summary['warn']}"
    )

    return success_response(
        data={
            "submission_id": submission_id,
            "summary": summary,
            "results": results,
        },
        message="Validation completed successfully",
    )


# ── GET /v1/analysis/submissions/{submission_id}/decision ─────────────────
@router.get(
    "/submissions/{submission_id}/decision",
    summary="Get routing decision",
    description=(
        "Computes the routing decision for a submission based on confidence "
        "scores and validation results. \n\n"
        "**Decision values:**\n"
        "- `auto` — all fields meet the high-confidence threshold, "
        "submission can be processed automatically\n"
        "- `review` — some fields have medium confidence or conflicts detected, "
        "senior review recommended\n"
        "- `manual` — one or more fields below the low threshold or "
        "validation failures present, manual input required\n\n"
        "Thresholds are configurable via `PUT /v1/config/thresholds`. "
        "Default: auto ≥ 85%, manual < 60%."
    ),
    response_description="Decision computed successfully",
    responses={
        200: {
            "description": "Decision computed successfully",
            "content": {
                "application/json": {
                    "examples": {
                        "auto": {
                            "summary": "All fields auto-process",
                            "value": {
                                "success": True,
                                "message": "Decision computed successfully",
                                "data": {
                                    "submission_id": "sub_k9m2xp12",
                                    "overallDecision": "auto",
                                    "reason": (
                                        "All fields meet the auto-process "
                                        "confidence threshold"
                                    ),
                                    "thresholds": {
                                        "autoAbove": 85,
                                        "manualBelow": 60,
                                    },
                                    "summary": {
                                        "auto": 8,
                                        "review": 0,
                                        "manual": 0,
                                    },
                                    "fieldDecisions": [
                                        {
                                            "field": "Full Name",
                                            "value": "Emeka Obi",
                                            "confidence": 94,
                                            "decision": "auto",
                                            "hasConflict": False,
                                            "isMissing": False,
                                        }
                                    ],
                                },
                            },
                        },
                        "review": {
                            "summary": "Conflict detected — flag for review",
                            "value": {
                                "success": True,
                                "message": "Decision computed successfully",
                                "data": {
                                    "submission_id": "sub_k9m2xp12",
                                    "overallDecision": "review",
                                    "reason": (
                                        "1 conflict(s) detected; "
                                        "senior review recommended"
                                    ),
                                    "thresholds": {
                                        "autoAbove": 85,
                                        "manualBelow": 60,
                                    },
                                    "summary": {
                                        "auto": 6,
                                        "review": 2,
                                        "manual": 0,
                                    },
                                    "fieldDecisions": [
                                        {
                                            "field": "Full Name",
                                            "value": "Emeka Obi",
                                            "confidence": 94,
                                            "decision": "auto",
                                            "hasConflict": True,
                                            "isMissing": False,
                                        }
                                    ],
                                },
                            },
                        },
                        "manual": {
                            "summary": "Low confidence — manual input required",
                            "value": {
                                "success": True,
                                "message": "Decision computed successfully",
                                "data": {
                                    "submission_id": "sub_k9m2xp12",
                                    "overallDecision": "manual",
                                    "reason": (
                                        "2 field(s) require manual input; "
                                        "1 validation failure(s)"
                                    ),
                                    "thresholds": {
                                        "autoAbove": 85,
                                        "manualBelow": 60,
                                    },
                                    "summary": {
                                        "auto": 5,
                                        "review": 1,
                                        "manual": 2,
                                    },
                                    "fieldDecisions": [
                                        {
                                            "field": "Address",
                                            "value": None,
                                            "confidence": 0,
                                            "decision": "manual",
                                            "hasConflict": False,
                                            "isMissing": True,
                                        }
                                    ],
                                },
                            },
                        },
                    }
                }
            },
        },
        404: _404_submission,
    },
)
def get_decision(
    submission_id: str,
    db: Session = db_dependency,
):
    submission = _get_submission_or_404(submission_id, db)
    classified = _get_classified_documents(submission_id, db)
    record = build_unified_record(classified)
    rules = db.query(ValidationRule).all()
    validation_results = run_rules(record, rules)

    # Load per-process field configs — controls which fields affect routing
    # and whether null values route to manual
    extraction_fields = (
        db.query(ProcessExtractionField)
        .filter(
            ProcessExtractionField.process_id == submission.process_id,
            ProcessExtractionField.is_active.is_(True),
        )
        .all()
    )

    # Build field_configs dict — None if no fields configured
    # (falls back to legacy behaviour in compute_decision)
    field_configs = (
        {
            f.name: {
                "include_in_decision": f.include_in_decision,
                "null_is_manual": f.null_is_manual,
            }
            for f in extraction_fields
        }
        if extraction_fields
        else None
    )

    decision = compute_decision(
        record,
        validation_results,
        thresholds=get_current_thresholds(),
        field_configs=field_configs,
    )

    logger.info(
        f"Decision: submission={submission_id} "
        f"overall={decision['overallDecision']}"
        f"field_configs={'configured' if field_configs else 'none'}"
    )

    return success_response(
        data={"submission_id": submission_id, **decision},
        message="Decision computed successfully",
    )
