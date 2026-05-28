"""
Per-process extraction field configuration.

Fields are tied to individual documents in the process checklist,
not to the process as a whole. This enables precise extraction —
each document type declares exactly which fields it should contain.

Endpoints:
    POST   /v1/processes/{pid}/documents/{did}/fields
           Add a field to a checklist document

    GET    /v1/processes/{pid}/documents/{did}/fields
           List all fields for a checklist document

    GET    /v1/processes/{pid}/documents/{did}/fields/{fid}
           Get a single field

    PATCH  /v1/processes/{pid}/documents/{did}/fields/{fid}
           Update a field

    DELETE /v1/processes/{pid}/documents/{did}/fields/{fid}
           Remove a field

    GET    /v1/processes/{pid}/fields/summary
           Get field configuration summary across all documents
           in the process — shows extraction_enabled status

Extraction rules:
  - A document with no active fields is classified only (type identified,
    no fields extracted)
  - A process where NO document has any fields configured is fully disabled —
    documents are stored but not sent to Claude
  - There is no fallback and no hardcoded field list
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from config.dependencies import get_db, verify_api_key
from config.logging import get_logger
from db.models import Process, ProcessDocument, ProcessDocumentField
from schemas.base import error_response, success_response
from schemas.config import ProcessThresholdUpdate
from schemas.extraction_field import (
    DocumentFieldCreate,
    DocumentFieldUpdate,
    ProcessRuleCreate,
)

logger = get_logger(__name__)

# ── Module-level dependencies ──────────────────────────────────────────────
db_dependency = Depends(get_db)
auth_dependency = Depends(verify_api_key)

# ── Shared response dicts ──────────────────────────────────────────────────
_401 = {
    "description": "Missing or invalid API key",
    "content": {
        "application/json": {
            "example": {
                "success": False,
                "message": "Invalid or missing API key",
                "data": None,
            }
        }
    },
}
_404_process = {
    "description": "Process not found",
    "content": {
        "application/json": {
            "example": {
                "success": False,
                "message": "Process not found",
                "data": None,
            }
        }
    },
}
_404_document = {
    "description": "Checklist document not found",
    "content": {
        "application/json": {
            "example": {
                "success": False,
                "message": "Checklist document not found",
                "data": None,
            }
        }
    },
}
_404_field = {
    "description": "Extraction field not found",
    "content": {
        "application/json": {
            "example": {
                "success": False,
                "message": "Extraction field not found",
                "data": None,
            }
        }
    },
}
_409 = {
    "description": "Field name already exists for this document",
    "content": {
        "application/json": {
            "example": {
                "success": False,
                "message": "Field 'Full Name' already exists for this document",
                "data": {"existing_id": "pdf_1a2b3c4d5e6f"},
            }
        }
    },
}
_422 = {
    "description": "Validation error",
    "content": {
        "application/json": {
            "example": {
                "success": False,
                "message": "Field name already exists for this process",
                "data": None,
            }
        }
    },
}
_500 = {
    "description": "Unexpected server error",
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
def _get_process_or_404(process_id: str, db: Session) -> Process:
    process = (
        db.query(Process)
        .filter(Process.id == process_id, Process.is_active.is_(True))
        .first()
    )
    if not process:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_response("Process not found"),
        )
    return process


def _get_checklist_doc_or_404(
    doc_id: int, process_id: str, db: Session
) -> ProcessDocument:
    doc = (
        db.query(ProcessDocument)
        .filter(
            ProcessDocument.id == doc_id,
            ProcessDocument.process_id == process_id,
        )
        .first()
    )
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_response("Checklist document not found"),
        )
    return doc


def _get_field_or_404(field_id: str, doc_id: int, db: Session) -> ProcessDocumentField:
    field = (
        db.query(ProcessDocumentField)
        .filter(
            ProcessDocumentField.id == field_id,
            ProcessDocumentField.process_document_id == doc_id,
        )
        .first()
    )
    if not field:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_response("Extraction field not found"),
        )
    return field


def _build_field_out(field: ProcessDocumentField) -> dict:
    return {
        "id": field.id,
        "process_document_id": field.process_document_id,
        "name": field.name,
        "description": field.description,
        "is_active": field.is_active,
        "include_in_decision": field.include_in_decision,
        "null_is_manual": field.null_is_manual,
        "sort_order": field.sort_order,
        "created_at": (field.created_at.isoformat() if field.created_at else None),
    }


def _build_doc_field_summary(doc: ProcessDocument) -> dict:
    """Build field summary for one checklist document."""
    fields = sorted(doc.extraction_fields, key=lambda f: f.sort_order)
    active = [f for f in fields if f.is_active]
    return {
        "process_document_id": doc.id,
        "document_name": doc.name,
        "items": [_build_field_out(f) for f in fields],
        "total": len(fields),
        "active": len(active),
        "fields_configured": len(active) > 0,
    }


# ── GET /v1/processes/{pid}/fields/summary ────────────────────────────────
@router.get(
    "/{process_id}/fields/summary",
    summary="Get extraction field summary for a process",
    description=(
        "Returns the field configuration status across all documents in "
        "the process checklist. Use this to determine whether extraction "
        "is enabled and which documents still need fields configured.\n\n"
        "**extraction_enabled** is `true` if at least one document in the "
        "process has at least one active extraction field. If `false`, "
        "no AI classification will run for any document uploaded to this "
        "process."
    ),
    responses={
        200: {
            "description": "Field summary retrieved",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "message": "Field summary retrieved successfully",
                        "data": {
                            "process_id": "proc_1a2b3c4d5e6f",
                            "total_documents": 3,
                            "documents_with_fields": 2,
                            "documents_without_fields": 1,
                            "extraction_enabled": True,
                            "documents": [
                                {
                                    "process_document_id": 1,
                                    "document_name": "National ID / NIN Slip",
                                    "total": 5,
                                    "active": 5,
                                    "fields_configured": True,
                                    "items": [],
                                },
                                {
                                    "process_document_id": 2,
                                    "document_name": "Bank Statement",
                                    "total": 0,
                                    "active": 0,
                                    "fields_configured": False,
                                    "items": [],
                                },
                            ],
                        },
                    }
                }
            },
        },
        404: _404_process,
    },
)
def get_fields_summary(
    process_id: str,
    db: Session = db_dependency,
):
    process = _get_process_or_404(process_id, db)
    docs = sorted(process.documents, key=lambda d: d.sort_order)

    doc_summaries = [_build_doc_field_summary(d) for d in docs]
    docs_with_fields = sum(1 for d in doc_summaries if d["fields_configured"])
    extraction_enabled = docs_with_fields > 0

    logger.info(
        f"Field summary: process={process_id} "
        f"docs={len(docs)} with_fields={docs_with_fields} "
        f"extraction_enabled={extraction_enabled}"
    )

    return success_response(
        data={
            "process_id": process_id,
            "total_documents": len(docs),
            "documents_with_fields": docs_with_fields,
            "documents_without_fields": len(docs) - docs_with_fields,
            "extraction_enabled": extraction_enabled,
            "documents": doc_summaries,
        },
        message="Field summary retrieved successfully",
    )


# ── POST /v1/processes/{pid}/documents/{did}/fields ───────────────────────
@router.post(
    "/{process_id}/documents/{doc_id}/fields",
    status_code=status.HTTP_201_CREATED,
    summary="Add an extraction field to a checklist document",
    description=(
        "Adds a field to a specific document in the process checklist. "
        "When a submitted document is classified as this document type, "
        "Claude will attempt to extract this field.\n\n"
        "Fields are unique per checklist document — you cannot add the "
        "same field name twice to the same document. The same field name "
        "can appear on different documents (e.g. 'Full Name' on both "
        "NIN Slip and Bank Statement)."
    ),
    responses={
        201: {
            "description": "Field added successfully",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "message": "Extraction field added successfully",
                        "data": {
                            "id": "pdf_1a2b3c4d5e6f",
                            "process_document_id": 1,
                            "name": "NIN",
                            "description": "11-digit National Identification Number",
                            "is_active": True,
                            "include_in_decision": True,
                            "null_is_manual": True,
                            "sort_order": 1,
                            "created_at": "2026-05-20T10:00:00+00:00",
                            "fields_configured": True,
                            "active_count": 1,
                        },
                    }
                }
            },
        },
        404: _404_document,
        409: _409,
    },
)
def add_document_field(
    process_id: str,
    doc_id: int,
    payload: DocumentFieldCreate,
    db: Session = db_dependency,
):
    _get_process_or_404(process_id, db)
    checklist_doc = _get_checklist_doc_or_404(doc_id, process_id, db)

    # Duplicate check within this document
    existing = (
        db.query(ProcessDocumentField)
        .filter(
            ProcessDocumentField.process_document_id == doc_id,
            ProcessDocumentField.name == payload.name,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=error_response(
                f"Field '{payload.name}' already exists for " f"'{checklist_doc.name}'",
                data={"existing_id": existing.id},
            ),
        )

    field = ProcessDocumentField(
        process_document_id=doc_id,
        name=payload.name,
        description=payload.description,
        include_in_decision=payload.include_in_decision,
        null_is_manual=payload.null_is_manual,
        sort_order=payload.sort_order,
        is_active=True,
    )
    db.add(field)
    db.commit()
    db.refresh(field)

    active_count = (
        db.query(ProcessDocumentField)
        .filter(
            ProcessDocumentField.process_document_id == doc_id,
            ProcessDocumentField.is_active.is_(True),
        )
        .count()
    )

    logger.info(
        f"Field added: {field.id} ('{field.name}') to document "
        f"'{checklist_doc.name}' ({doc_id}) in process {process_id}"
    )

    return success_response(
        data={
            **_build_field_out(field),
            "active_count": active_count,
            "fields_configured": active_count > 0,
        },
        message="Extraction field added successfully",
    )


# ── GET /v1/processes/{pid}/documents/{did}/fields ────────────────────────
@router.get(
    "/{process_id}/documents/{doc_id}/fields",
    summary="List extraction fields for a checklist document",
    description=(
        "Returns all extraction fields configured for a specific document "
        "in the process checklist, ordered by sort_order.\n\n"
        "If `fields_configured` is `false`, this document will be "
        "classified (type identified) but no fields will be extracted "
        "from it."
    ),
    responses={
        200: {
            "description": "Fields retrieved",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "message": "Extraction fields retrieved successfully",
                        "data": {
                            "process_document_id": 1,
                            "document_name": "National ID / NIN Slip",
                            "items": [],
                            "total": 0,
                            "active": 0,
                            "fields_configured": False,
                        },
                    }
                }
            },
        },
        404: _404_document,
    },
)
def list_document_fields(
    process_id: str,
    doc_id: int,
    db: Session = db_dependency,
):
    _get_process_or_404(process_id, db)
    checklist_doc = _get_checklist_doc_or_404(doc_id, process_id, db)

    fields = (
        db.query(ProcessDocumentField)
        .filter(ProcessDocumentField.process_document_id == doc_id)
        .order_by(ProcessDocumentField.sort_order.asc())
        .all()
    )
    active = [f for f in fields if f.is_active]

    return success_response(
        data={
            "process_document_id": doc_id,
            "document_name": checklist_doc.name,
            "items": [_build_field_out(f) for f in fields],
            "total": len(fields),
            "active": len(active),
            "fields_configured": len(active) > 0,
        },
        message="Extraction fields retrieved successfully",
    )


# ── GET /v1/processes/{pid}/documents/{did}/fields/{fid} ──────────────────
@router.get(
    "/{process_id}/documents/{doc_id}/fields/{field_id}",
    summary="Get a single extraction field",
    responses={200: {}, 404: _404_field},
)
def get_document_field(
    process_id: str,
    doc_id: int,
    field_id: str,
    db: Session = db_dependency,
):
    _get_process_or_404(process_id, db)
    _get_checklist_doc_or_404(doc_id, process_id, db)
    field = _get_field_or_404(field_id, doc_id, db)

    return success_response(
        data=_build_field_out(field),
        message="Extraction field retrieved successfully",
    )


# ── PATCH /v1/processes/{pid}/documents/{did}/fields/{fid} ────────────────
@router.patch(
    "/{process_id}/documents/{doc_id}/fields/{field_id}",
    summary="Update an extraction field",
    description=(
        "Update field settings. All fields are optional — send only "
        "what you want to change.\n\n"
        "Disabling a field (`is_active: false`) removes it from Claude's "
        "extraction prompt without deleting the configuration."
    ),
    responses={200: {}, 404: _404_field},
)
def update_document_field(
    process_id: str,
    doc_id: int,
    field_id: str,
    payload: DocumentFieldUpdate,
    db: Session = db_dependency,
):
    _get_process_or_404(process_id, db)
    _get_checklist_doc_or_404(doc_id, process_id, db)
    field = _get_field_or_404(field_id, doc_id, db)

    if payload.description is not None:
        field.description = payload.description
    if payload.is_active is not None:
        field.is_active = payload.is_active
    if payload.include_in_decision is not None:
        field.include_in_decision = payload.include_in_decision
    if payload.null_is_manual is not None:
        field.null_is_manual = payload.null_is_manual
    if payload.sort_order is not None:
        field.sort_order = payload.sort_order

    db.commit()
    db.refresh(field)

    active_count = (
        db.query(ProcessDocumentField)
        .filter(
            ProcessDocumentField.process_document_id == doc_id,
            ProcessDocumentField.is_active.is_(True),
        )
        .count()
    )

    logger.info(
        f"Field updated: {field_id} ('{field.name}') in doc {doc_id} "
        f"— {active_count} active fields remaining"
    )

    return success_response(
        data={
            **_build_field_out(field),
            "active_count": active_count,
            "fields_configured": active_count > 0,
        },
        message="Extraction field updated successfully",
    )


# ── DELETE /v1/processes/{pid}/documents/{did}/fields/{fid} ───────────────
@router.delete(
    "/{process_id}/documents/{doc_id}/fields/{field_id}",
    summary="Remove an extraction field",
    description=(
        "Permanently removes a field from a checklist document. "
        "This cannot be undone.\n\n"
        "Consider disabling (`is_active: false`) instead of deleting "
        "if you may want to re-enable the field later."
    ),
    responses={200: {}, 404: _404_field},
)
def delete_document_field(
    process_id: str,
    doc_id: int,
    field_id: str,
    db: Session = db_dependency,
):
    _get_process_or_404(process_id, db)
    _get_checklist_doc_or_404(doc_id, process_id, db)
    field = _get_field_or_404(field_id, doc_id, db)

    field_name = field.name
    db.delete(field)
    db.commit()

    active_count = (
        db.query(ProcessDocumentField)
        .filter(
            ProcessDocumentField.process_document_id == doc_id,
            ProcessDocumentField.is_active.is_(True),
        )
        .count()
    )

    logger.info(
        f"Field deleted: {field_id} ('{field_name}') from doc {doc_id} "
        f"in process {process_id}"
    )

    return success_response(
        data={
            "id": field_id,
            "name": field_name,
            "active_count": active_count,
            "fields_configured": active_count > 0,
        },
        message="Extraction field removed successfully",
    )


# ── GET /v1/processes/{pid}/rules ─────────────────────────────────────────
@router.get(
    "/{process_id}/rules",
    summary="List validation rules for a process",
    description=(
        "Returns all validation rules that apply to this process — "
        "both global rules (process_id is null) and rules scoped "
        "specifically to this process.\n\n"
        "Use this endpoint to see the complete set of rules that "
        "will run when this process's submissions are validated."
    ),
    responses={
        200: {
            "description": "Rules retrieved",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "message": "Validation rules retrieved successfully",
                        "data": {
                            "items": [],
                            "total": 0,
                            "global_count": 0,
                            "process_count": 0,
                            "enabled": 0,
                        },
                    }
                }
            },
        },
        404: _404_process,
    },
)
def list_process_rules(
    process_id: str,
    db: Session = db_dependency,
):
    from sqlalchemy import or_

    from db.models import ValidationRule

    _get_process_or_404(process_id, db)

    rules = (
        db.query(ValidationRule)
        .filter(
            or_(
                ValidationRule.process_id.is_(None),
                ValidationRule.process_id == process_id,
            )
        )
        .order_by(ValidationRule.created_at.asc())
        .all()
    )

    global_count = sum(1 for r in rules if r.process_id is None)
    process_count = sum(1 for r in rules if r.process_id is not None)
    enabled = sum(1 for r in rules if r.is_enabled)

    return success_response(
        data={
            "items": [
                {
                    "id": r.id,
                    "name": r.name,
                    "rule_type": r.rule_type,
                    "field": r.field,
                    "check": r.check,
                    "pattern": r.pattern,
                    "severity": r.severity,
                    "is_enabled": r.is_enabled,
                    "process_id": r.process_id,
                    "scope": "global" if r.process_id is None else "process",
                    "created_at": (r.created_at.isoformat() if r.created_at else None),
                }
                for r in rules
            ],
            "total": len(rules),
            "global_count": global_count,
            "process_count": process_count,
            "enabled": enabled,
        },
        message="Validation rules retrieved successfully",
    )


# ── POST /v1/processes/{pid}/rules ────────────────────────────────────────
@router.post(
    "/{process_id}/rules",
    status_code=status.HTTP_201_CREATED,
    summary="Create a process-scoped validation rule",
    description=(
        "Creates a validation rule scoped to this process only. "
        "This rule will run in addition to global rules when validating "
        "submissions under this process.\n\n"
        "To create a global rule that applies to all processes, use "
        "`POST /v1/config/rules` without a `process_id`."
    ),
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
                            "name": "Property value required",
                            "rule_type": "required",
                            "field": "Property Value",
                            "scope": "process",
                            "process_id": "proc_1a2b3c4d5e6f",
                        },
                    }
                }
            },
        },
        404: _404_process,
        422: {
            "description": "Duplicate rule name",
            "content": {
                "application/json": {
                    "example": {
                        "success": False,
                        "message": "A rule named 'Property value required' already exists",
                        "data": None,
                    }
                }
            },
        },
    },
)
def create_process_rule(
    process_id: str,
    payload: "ProcessRuleCreate",
    db: Session = db_dependency,
):
    from sqlalchemy import or_

    from db.models import ValidationRule

    _get_process_or_404(process_id, db)

    # Duplicate check within this process scope
    existing = (
        db.query(ValidationRule)
        .filter(
            ValidationRule.name.ilike(payload.name),
            or_(
                ValidationRule.process_id == process_id,
                ValidationRule.process_id.is_(None),
            ),
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=error_response(
                f"A rule named '{payload.name}' already exists",
                data={"existing_id": existing.id},
            ),
        )

    rule = ValidationRule(
        name=payload.name,
        rule_type=payload.rule_type,
        field=payload.field,
        severity=payload.severity,
        pattern=payload.pattern,
        check=payload.check,
        process_id=process_id,
        is_enabled=True,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)

    logger.info(
        f"Process rule created: {rule.id} ({rule.name}) " f"for process {process_id}"
    )

    return success_response(
        data={
            "id": rule.id,
            "name": rule.name,
            "rule_type": rule.rule_type,
            "field": rule.field,
            "check": rule.check,
            "pattern": rule.pattern,
            "severity": rule.severity,
            "is_enabled": rule.is_enabled,
            "process_id": rule.process_id,
            "scope": "process",
            "created_at": (rule.created_at.isoformat() if rule.created_at else None),
        },
        message="Validation rule created successfully",
    )


# ── GET /v1/processes/{pid}/thresholds ────────────────────────────────────
@router.get(
    "/{process_id}/thresholds",
    summary="Get confidence thresholds for a process",
    description=(
        "Returns the confidence thresholds that apply to this process.\n\n"
        "If the process has its own threshold configuration, those values "
        "are returned with `is_override: true`.\n\n"
        "If no process-specific thresholds are configured, the global "
        "default thresholds are returned with `is_override: false`.\n\n"
        "Use `PUT /v1/processes/{id}/thresholds` to set an override."
    ),
    responses={
        200: {
            "description": "Thresholds retrieved",
            "content": {
                "application/json": {
                    "examples": {
                        "override": {
                            "summary": "Process has its own thresholds",
                            "value": {
                                "success": True,
                                "message": "Thresholds retrieved successfully",
                                "data": {
                                    "auto_above": 90,
                                    "manual_below": 70,
                                    "scope": "process",
                                    "process_id": "proc_1a2b3c4d5e6f",
                                    "is_override": True,
                                },
                            },
                        },
                        "global": {
                            "summary": "Using global default",
                            "value": {
                                "success": True,
                                "message": "Thresholds retrieved successfully",
                                "data": {
                                    "auto_above": 85,
                                    "manual_below": 60,
                                    "scope": "global",
                                    "process_id": None,
                                    "is_override": False,
                                },
                            },
                        },
                    }
                }
            },
        },
        404: _404_process,
    },
)
def get_process_thresholds(
    process_id: str,
    db: Session = db_dependency,
):
    from db.models import ProcessThreshold
    from routers.config import _ensure_global_threshold

    _get_process_or_404(process_id, db)

    # Check for process-specific override
    process_row = (
        db.query(ProcessThreshold)
        .filter(ProcessThreshold.process_id == process_id)
        .first()
    )

    if process_row:
        return success_response(
            data={
                "auto_above": process_row.auto_above,
                "manual_below": process_row.manual_below,
                "scope": "process",
                "process_id": process_id,
                "is_override": True,
                "description": {
                    "auto": (f"confidence ≥ {process_row.auto_above}% → auto-process"),
                    "review": (
                        f"{process_row.manual_below}% ≤ confidence "
                        f"< {process_row.auto_above}% → review"
                    ),
                    "manual": (
                        f"confidence < {process_row.manual_below}% → manual input"
                    ),
                },
            },
            message="Thresholds retrieved successfully",
        )

    # Fall back to global
    global_row = _ensure_global_threshold(db)
    return success_response(
        data={
            "auto_above": global_row.auto_above,
            "manual_below": global_row.manual_below,
            "scope": "global",
            "process_id": None,
            "is_override": False,
            "description": {
                "auto": (f"confidence ≥ {global_row.auto_above}% → auto-process"),
                "review": (
                    f"{global_row.manual_below}% ≤ confidence "
                    f"< {global_row.auto_above}% → review"
                ),
                "manual": (f"confidence < {global_row.manual_below}% → manual input"),
            },
        },
        message="Thresholds retrieved successfully (using global default)",
    )


# ── PUT /v1/processes/{pid}/thresholds ────────────────────────────────────
@router.put(
    "/{process_id}/thresholds",
    summary="Set confidence thresholds for a process",
    description=(
        "Creates or updates confidence thresholds specific to this process, "
        "overriding the global default.\n\n"
        "Use this when a process requires stricter or more lenient thresholds "
        "than the global default — for example, RSA Mortgage might require "
        "≥ 90% confidence for auto-processing while a simpler benefits "
        "workflow might use ≥ 80%.\n\n"
        "To revert to the global default, use "
        "`DELETE /v1/processes/{id}/thresholds`."
    ),
    responses={
        200: {
            "description": "Process thresholds set",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "message": "Process thresholds updated successfully",
                        "data": {
                            "auto_above": 90,
                            "manual_below": 70,
                            "scope": "process",
                            "process_id": "proc_1a2b3c4d5e6f",
                            "is_override": True,
                        },
                    }
                }
            },
        },
        404: _404_process,
        422: {
            "description": "Invalid threshold values",
            "content": {
                "application/json": {
                    "example": {
                        "success": False,
                        "message": "auto_above must be greater than manual_below",
                        "data": None,
                    }
                }
            },
        },
    },
)
def set_process_thresholds(
    process_id: str,
    payload: "ProcessThresholdUpdate",
    db: Session = db_dependency,
):
    from db.models import ProcessThreshold
    from schemas.config import ProcessThresholdUpdate

    _get_process_or_404(process_id, db)

    if payload.auto_above <= payload.manual_below:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=error_response(
                f"auto_above ({payload.auto_above}) must be greater than "
                f"manual_below ({payload.manual_below})"
            ),
        )

    # Upsert — create if not exists, update if exists
    row = (
        db.query(ProcessThreshold)
        .filter(ProcessThreshold.process_id == process_id)
        .first()
    )

    if row:
        previous = {"auto_above": row.auto_above, "manual_below": row.manual_below}
        row.auto_above = payload.auto_above
        row.manual_below = payload.manual_below
    else:
        previous = None
        row = ProcessThreshold(
            process_id=process_id,
            auto_above=payload.auto_above,
            manual_below=payload.manual_below,
        )
        db.add(row)

    db.commit()
    db.refresh(row)

    logger.info(
        f"Process thresholds set: process={process_id} "
        f"auto≥{payload.auto_above}% manual<{payload.manual_below}%"
    )

    return success_response(
        data={
            "auto_above": row.auto_above,
            "manual_below": row.manual_below,
            "scope": "process",
            "process_id": process_id,
            "is_override": True,
            "previous": previous,
            "description": {
                "auto": f"confidence ≥ {row.auto_above}% → auto-process",
                "review": (
                    f"{row.manual_below}% ≤ confidence " f"< {row.auto_above}% → review"
                ),
                "manual": f"confidence < {row.manual_below}% → manual input",
            },
        },
        message="Process thresholds updated successfully",
    )


# ── DELETE /v1/processes/{pid}/thresholds ─────────────────────────────────
@router.delete(
    "/{process_id}/thresholds",
    summary="Remove process threshold override",
    description=(
        "Removes the process-specific threshold configuration, reverting "
        "this process to use the global default thresholds.\n\n"
        "If no process-specific threshold exists, returns 200 with no action."
    ),
    responses={
        200: {
            "description": "Process threshold override removed",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "message": "Process threshold override removed. "
                        "Now using global defaults.",
                        "data": {
                            "process_id": "proc_1a2b3c4d5e6f",
                            "reverted_to_global": True,
                            "global_auto_above": 85,
                            "global_manual_below": 60,
                        },
                    }
                }
            },
        },
        404: _404_process,
    },
)
def delete_process_thresholds(
    process_id: str,
    db: Session = db_dependency,
):
    from db.models import ProcessThreshold
    from routers.config import _ensure_global_threshold

    _get_process_or_404(process_id, db)

    row = (
        db.query(ProcessThreshold)
        .filter(ProcessThreshold.process_id == process_id)
        .first()
    )

    if row:
        db.delete(row)
        db.commit()
        logger.info(f"Process threshold override removed: {process_id}")

    global_row = _ensure_global_threshold(db)

    return success_response(
        data={
            "process_id": process_id,
            "reverted_to_global": True,
            "global_auto_above": global_row.auto_above,
            "global_manual_below": global_row.manual_below,
        },
        message="Process threshold override removed. Now using global defaults.",
    )
