"""
Per-process extraction field configuration.

    POST   /v1/processes/{id}/fields         Add a field to a process
    GET    /v1/processes/{id}/fields         List all fields for a process
    GET    /v1/processes/{id}/fields/{fid}   Get a single field
    PATCH  /v1/processes/{id}/fields/{fid}   Update field settings
    DELETE /v1/processes/{id}/fields/{fid}   Remove a field

If a process has no active extraction fields, AI classification
is disabled — documents are stored but not sent to Claude.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from config.dependencies import get_db, verify_api_key
from config.logging import get_logger
from db.models import Process, ProcessExtractionField
from schemas.base import error_response, success_response
from schemas.extraction_field import ExtractionFieldCreate, ExtractionFieldUpdate

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


def _get_field_or_404(
    field_id: str, process_id: str, db: Session
) -> ProcessExtractionField:
    field = (
        db.query(ProcessExtractionField)
        .filter(
            ProcessExtractionField.id == field_id,
            ProcessExtractionField.process_id == process_id,
        )
        .first()
    )
    if not field:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_response("Extraction field not found"),
        )
    return field


def _build_field_out(field: ProcessExtractionField) -> dict:
    return {
        "id": field.id,
        "process_id": field.process_id,
        "name": field.name,
        "description": field.description,
        "is_active": field.is_active,
        "include_in_decision": field.include_in_decision,
        "null_is_manual": field.null_is_manual,
        "sort_order": field.sort_order,
        "created_at": (field.created_at.isoformat() if field.created_at else None),
    }


# ── POST /v1/processes/{id}/fields ────────────────────────────────────────
@router.post(
    "/{process_id}/fields",
    status_code=status.HTTP_201_CREATED,
    summary="Add an extraction field to a process",
    description=(
        "Adds a field to the process extraction configuration. "
        "Claude will extract this field from all documents uploaded "
        "to this process. At least one active field must exist for "
        "extraction to be enabled."
    ),
    responses={
        201: {
            "description": "Field added",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "message": "Extraction field added successfully",
                        "data": {
                            "id": "pef_1a2b3c4d5e6f",
                            "process_id": "proc_1a2b3c4d5e6f",
                            "name": "Full Name",
                            "is_active": True,
                            "include_in_decision": True,
                            "null_is_manual": True,
                        },
                    }
                }
            },
        },
        404: _404_process,
        422: _422,
    },
)
def add_extraction_field(
    process_id: str,
    payload: ExtractionFieldCreate,
    db: Session = db_dependency,
):
    _get_process_or_404(process_id, db)

    # Check for duplicate name within this process
    existing = (
        db.query(ProcessExtractionField)
        .filter(
            ProcessExtractionField.process_id == process_id,
            ProcessExtractionField.name == payload.name,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=error_response(
                f"Field '{payload.name}' already exists for this process",
                data={"existing_id": existing.id},
            ),
        )

    field = ProcessExtractionField(
        process_id=process_id,
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

    # Count active fields after addition
    active_count = (
        db.query(ProcessExtractionField)
        .filter(
            ProcessExtractionField.process_id == process_id,
            ProcessExtractionField.is_active.is_(True),
        )
        .count()
    )

    logger.info(
        f"Extraction field added: {field.id} ({field.name}) "
        f"for process {process_id} — {active_count} active fields"
    )
    return success_response(
        data=_build_field_out(field),
        message="Extraction field added successfully",
    )


# ── GET /v1/processes/{id}/fields ─────────────────────────────────────────
@router.get(
    "/{process_id}/fields",
    summary="List extraction fields for a process",
    description=(
        "Returns all extraction fields for a process ordered by sort_order. "
        "If extraction_enabled is false, no AI classification will run "
        "for documents uploaded to this process."
    ),
    responses={
        200: {
            "description": "Field list",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "message": "Extraction fields retrieved successfully",
                        "data": {
                            "items": [],
                            "total": 0,
                            "active": 0,
                            "extraction_enabled": False,
                        },
                    }
                }
            },
        },
        404: _404_process,
    },
)
def list_extraction_fields(
    process_id: str,
    db: Session = db_dependency,
):
    _get_process_or_404(process_id, db)

    fields = (
        db.query(ProcessExtractionField)
        .filter(ProcessExtractionField.process_id == process_id)
        .order_by(ProcessExtractionField.sort_order.asc())
        .all()
    )

    active = [f for f in fields if f.is_active]

    return success_response(
        data={
            "items": [_build_field_out(f) for f in fields],
            "total": len(fields),
            "active": len(active),
            "extraction_enabled": len(active) > 0,
        },
        message="Extraction fields retrieved successfully",
    )


# ── GET /v1/processes/{id}/fields/{fid} ───────────────────────────────────
@router.get(
    "/{process_id}/fields/{field_id}",
    summary="Get a single extraction field",
    responses={200: {}, 404: _404_field},
)
def get_extraction_field(
    process_id: str,
    field_id: str,
    db: Session = db_dependency,
):
    _get_process_or_404(process_id, db)
    field = _get_field_or_404(field_id, process_id, db)
    return success_response(
        data=_build_field_out(field),
        message="Extraction field retrieved successfully",
    )


# ── PATCH /v1/processes/{id}/fields/{fid} ────────────────────────────────
@router.patch(
    "/{process_id}/fields/{field_id}",
    summary="Update an extraction field",
    description=(
        "Update field settings. Disabling all fields will disable "
        "AI extraction for the entire process."
    ),
    responses={200: {}, 404: _404_field, 422: _422},
)
def update_extraction_field(
    process_id: str,
    field_id: str,
    payload: ExtractionFieldUpdate,
    db: Session = db_dependency,
):
    _get_process_or_404(process_id, db)
    field = _get_field_or_404(field_id, process_id, db)

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
        db.query(ProcessExtractionField)
        .filter(
            ProcessExtractionField.process_id == process_id,
            ProcessExtractionField.is_active.is_(True),
        )
        .count()
    )

    logger.info(
        f"Extraction field updated: {field_id} ({field.name}) — "
        f"process {process_id} now has {active_count} active fields"
    )
    return success_response(
        data={
            **_build_field_out(field),
            "extraction_enabled": active_count > 0,
        },
        message="Extraction field updated successfully",
    )


# ── DELETE /v1/processes/{id}/fields/{fid} ────────────────────────────────
@router.delete(
    "/{process_id}/fields/{field_id}",
    summary="Remove an extraction field",
    description=(
        "Permanently removes a field from the process configuration. "
        "This cannot be undone. If this was the last active field, "
        "extraction will be disabled for this process."
    ),
    responses={200: {}, 404: _404_field},
)
def delete_extraction_field(
    process_id: str,
    field_id: str,
    db: Session = db_dependency,
):
    _get_process_or_404(process_id, db)
    field = _get_field_or_404(field_id, process_id, db)

    field_name = field.name
    db.delete(field)
    db.commit()

    active_count = (
        db.query(ProcessExtractionField)
        .filter(
            ProcessExtractionField.process_id == process_id,
            ProcessExtractionField.is_active.is_(True),
        )
        .count()
    )

    logger.info(
        f"Extraction field removed: {field_id} ({field_name}) "
        f"from process {process_id} — {active_count} active fields remaining"
    )
    return success_response(
        data={
            "id": field_id,
            "name": field_name,
            "extraction_enabled": active_count > 0,
        },
        message="Extraction field removed successfully",
    )
