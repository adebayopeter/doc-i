"""
Processes router — /v1/processes

Endpoints:
    POST   /v1/processes              Create a new process
    GET    /v1/processes              List all active processes
    GET    /v1/processes/{process_id} Get process with document checklist
    DELETE /v1/processes/{process_id} Deactivate a process (soft delete)
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from config.dependencies import get_db, verify_api_key
from config.logging import get_logger
from db.models import Process, ProcessDocument
from schemas.base import error_response, success_response
from schemas.process import (
    ProcessCreate,
    ProcessDeactivateData,
    ProcessDetail,
    ProcessDocumentOut,
    ProcessListData,
    ProcessSummary,
    ProcessUpdate,
)

logger = get_logger(__name__)

# ── Module-level dependencies ──────────────────────────────────────────────
db_dependency = Depends(get_db)
auth_dependency = Depends(verify_api_key)

# ── Shared error response examples ────────────────────────────────────────
# Defined once and reused across all endpoints to avoid repetition
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

_404 = {
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

_422 = {
    "description": "Validation error — request body failed schema validation",
    "content": {
        "application/json": {
            "example": {
                "success": False,
                "message": "name: field required | documents: list should have at least 1 item",
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
    responses={
        401: _401,
        404: _404,
        422: _422,
        500: _500,
    },
)


# ── Helpers ────────────────────────────────────────────────────────────────
def _get_process_or_404(process_id: str, db: Session) -> Process:
    """
    Fetch an active process by ID.
    Raises 404 if not found or deactivated.
    Used by multiple endpoints to avoid repetition.
    """
    process = (
        db.query(Process)
        .filter(Process.id == process_id, Process.is_active == True)  # noqa: E712
        .first()
    )
    if not process:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_response("Process not found"),
        )
    return process


def _build_process_summary(process: Process) -> ProcessSummary:
    """Build a compact ProcessSummary from a Process ORM object."""
    return ProcessSummary(
        process_id=process.id,
        name=process.name,
        description=process.description,
        document_count=len(process.documents),
        color_var=process.color_var,
        icon=process.icon,
        created_at=process.created_at,
    )


def _build_process_detail(process: Process) -> ProcessDetail:
    """Build a full ProcessDetail including document checklist."""
    return ProcessDetail(
        process_id=process.id,
        name=process.name,
        description=process.description,
        color_var=process.color_var,
        icon=process.icon,
        document_count=len(process.documents),
        documents=[
            ProcessDocumentOut(
                id=d.id,
                name=d.name,
                category=d.category,
                is_required=d.is_required,
                sort_order=d.sort_order,
            )
            for d in sorted(process.documents, key=lambda x: x.sort_order)
        ],
        created_at=process.created_at,
    )


# ── POST /v1/processes ─────────────────────────────────────────────────────
@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Create a new process",
    description=(
        "Creates a reusable process definition with a required document checklist. "
        "Returns the process ID to use in all downstream submission calls. "
        "The AI classifier uses the document list to classify uploaded files — "
        "no training required."
    ),
    response_description="Process created successfully",
    responses={
        201: {
            "description": "Process created successfully",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "message": "Process created successfully",
                        "data": {
                            "process_id": "proc_a1b2c3d4e5f6",
                            "name": "RSA Mortgage",
                            "description": (
                                "Residential mortgage application"
                                " — 22 required documents"
                            ),
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
                                {
                                    "id": 3,
                                    "name": "Offer letter",
                                    "category": "Income",
                                    "is_required": False,
                                    "sort_order": 2,
                                },
                            ],
                            "created_at": "2025-05-20T10:00:00Z",
                        },
                    }
                }
            },
        },
        409: {
            "description": "A process with this name already exists",
            "content": {
                "application/json": {
                    "example": {
                        "success": False,
                        "message": "A process named 'RSA Mortgage' already exists",
                        "data": {"existing_process_id": "proc_a1b2c3d4e5f6"},
                    }
                }
            },
        },
        422: _422,
    },
)
def create_process(
    payload: ProcessCreate,
    db: Session = db_dependency,
):
    """
    Create a new document workflow process.

    Each process defines:
    - A name and description e.g. "RSA Mortgage"
    - A list of required documents e.g. NIN slip, bank statement
    - Optional UI configuration (color, icon)

    The document list is passed to Claude AI on every document upload,
    so it can classify the uploaded file against the correct checklist.
    """
    logger.info(f"Creating process: {payload.name}")

    # Check for duplicate name
    existing = (
        db.query(Process)
        .filter(Process.name == payload.name, Process.is_active == True)  # noqa: E712
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=error_response(
                f"A process named '{payload.name}' already exists",
                data={"existing_process_id": existing.id},
            ),
        )

    # Create the process
    process = Process(
        name=payload.name,
        description=payload.description,
        color_var=payload.color_var,
        icon=payload.icon,
    )
    db.add(process)
    db.flush()  # get the ID without committing

    # Create the document checklist
    for index, doc in enumerate(payload.documents):
        db.add(
            ProcessDocument(
                process_id=process.id,
                name=doc.name,
                category=doc.category,
                is_required=doc.is_required,
                sort_order=index,
            )
        )

    db.commit()
    db.refresh(process)

    logger.info(
        f"Process created: {process.id} " f"with {len(payload.documents)} documents"
    )

    return success_response(
        message="Process created successfully",
        data=_build_process_detail(process),
    )


# ── GET /v1/processes ──────────────────────────────────────────────────────
@router.get(
    "",
    summary="List all processes",
    description=(
        "Returns all active processes. "
        "Each item includes a document count but not the full checklist. "
        "Use GET /v1/processes/{process_id} to get the full document list."
    ),
    response_description="List of processes retrieved successfully",
    responses={
        200: {
            "description": "Processes retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "message": "Processes retrieved successfully",
                        "data": {
                            "items": [
                                {
                                    "process_id": "proc_a1b2c3d4e5f6",
                                    "name": "RSA Mortgage",
                                    "description": ("Residential mortgage application"),
                                    "document_count": 22,
                                    "color_var": "info",
                                    "icon": "ti-home-2",
                                    "created_at": "2025-05-20T10:00:00Z",
                                },
                                {
                                    "process_id": "proc_b2c3d4e5f6a1",
                                    "name": "Benefit Application",
                                    "description": ("Government benefit eligibility"),
                                    "document_count": 10,
                                    "color_var": "success",
                                    "icon": "ti-coin",
                                    "created_at": "2025-05-20T11:00:00Z",
                                },
                                {
                                    "process_id": "proc_c3d4e5f6a1b2",
                                    "name": "Employee Onboarding",
                                    "description": (
                                        "New employee right-to-work checks"
                                    ),
                                    "document_count": 8,
                                    "color_var": "warning",
                                    "icon": "ti-users",
                                    "created_at": "2025-05-20T12:00:00Z",
                                },
                            ],
                            "total": 3,
                        },
                    }
                }
            },
        },
    },
)
def list_processes(db: Session = db_dependency):
    """
    List all active process definitions.
    """
    processes = (
        db.query(Process)
        .filter(Process.is_active == True)  # noqa: E712
        .order_by(Process.created_at.desc())
        .all()
    )

    logger.info(f"Listed {len(processes)} processes")

    return success_response(
        message="Processes retrieved successfully",
        data=ProcessListData(
            items=[_build_process_summary(p) for p in processes],
            total=len(processes),
        ),
    )


# ── GET /v1/processes/{process_id} ────────────────────────────────────────
@router.get(
    "/{process_id}",
    summary="Get a process",
    description=(
        "Returns full process details including the complete document checklist. "
        "The checklist is used by consuming apps to show applicants "
        "which documents they need to upload."
    ),
    response_description="Process retrieved successfully",
    responses={
        200: {
            "description": "Process retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "message": "Process retrieved successfully",
                        "data": {
                            "process_id": "proc_a1b2c3d4e5f6",
                            "name": "RSA Mortgage",
                            "description": (
                                "Residential mortgage application"
                                " — 22 required documents"
                            ),
                            "color_var": "info",
                            "icon": "ti-home-2",
                            "document_count": 5,
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
                                    "name": "Utility bill (proof of address)",
                                    "category": "Identity",
                                    "is_required": True,
                                    "sort_order": 1,
                                },
                                {
                                    "id": 3,
                                    "name": "Bank statement (6 months)",
                                    "category": "Financial",
                                    "is_required": True,
                                    "sort_order": 2,
                                },
                                {
                                    "id": 4,
                                    "name": "Offer letter / Employment letter",
                                    "category": "Income",
                                    "is_required": True,
                                    "sort_order": 3,
                                },
                                {
                                    "id": 5,
                                    "name": "Guarantor letter",
                                    "category": "Supporting",
                                    "is_required": False,
                                    "sort_order": 4,
                                },
                            ],
                            "created_at": "2025-05-20T10:00:00Z",
                        },
                    }
                }
            },
        },
        404: _404,
    },
)
def get_process(
    process_id: str,
    db: Session = db_dependency,
):
    """
    Get a single process with its full document checklist.
    """
    process = _get_process_or_404(process_id, db)

    logger.info(f"Retrieved process: {process_id}")

    return success_response(
        message="Process retrieved successfully",
        data=_build_process_detail(process),
    )


# ── UPDATE /v1/processes/{process_id} ────────────────────────────────────
@router.patch(
    "/{process_id}",
    summary="Update a process",
    description=(
        "Update process metadata or replace the document checklist. "
        "If documents are provided, the entire checklist is replaced. "
        "Cannot update a deactivated process."
    ),
    responses={
        200: {
            "description": "Process updated",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "message": "Process updated successfully",
                        "data": {
                            "process_id": "proc_1a2b3c4d5e6f",
                            "name": "RSA Mortgage Application",
                            "document_count": 6,
                        },
                    }
                }
            },
        },
        404: _404,
        422: _422,
    },
)
def update_process(
    process_id: str,
    payload: ProcessUpdate,
    db: Session = db_dependency,
):
    process = _get_process_or_404(process_id, db)

    if not process.is_active:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=error_response("Cannot update a deactivated process"),
        )

    # Check name uniqueness if name is being changed
    if payload.name and payload.name != process.name:
        conflict = (
            db.query(Process)
            .filter(
                Process.name == payload.name,
                Process.id != process_id,
                Process.is_active.is_(True),
            )
            .first()
        )
        if conflict:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=error_response(
                    f"A process named '{payload.name}' already exists",
                    data={"existing_id": conflict.id},
                ),
            )
        process.name = payload.name

    if payload.description is not None:
        process.description = payload.description
    if payload.color_var is not None:
        process.color_var = payload.color_var
    if payload.icon is not None:
        process.icon = payload.icon

    # Replace document checklist if provided
    if payload.documents is not None:
        # Delete existing documents
        db.query(ProcessDocument).filter(
            ProcessDocument.process_id == process_id
        ).delete(synchronize_session=False)

        # Add new documents
        for order, doc in enumerate(payload.documents, start=1):
            db.add(
                ProcessDocument(
                    process_id=process_id,
                    name=doc.name,
                    category=doc.category,
                    is_required=doc.is_required,
                    sort_order=order,
                )
            )

    db.commit()
    db.refresh(process)

    logger.info(f"Process updated: {process_id} ({process.name})")
    return success_response(
        data=_build_process_detail(process),
        message="Process updated successfully",
    )


# ── DELETE /v1/processes/{process_id} ────────────────────────────────────
@router.delete(
    "/{process_id}",
    status_code=status.HTTP_200_OK,
    summary="Deactivate a process",
    description=(
        "Soft deletes a process by setting is_active = false. "
        "Existing submissions linked to this process are not affected. "
        "The process will no longer appear in list results."
    ),
    response_description="Process deactivated successfully",
    responses={
        200: {
            "description": "Process deactivated successfully",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "message": "Process deactivated successfully",
                        "data": {
                            "process_id": "proc_a1b2c3d4e5f6",
                        },
                    }
                }
            },
        },
        404: _404,
    },
)
def delete_process(
    process_id: str,
    db: Session = db_dependency,
):
    """
    Deactivate a process — soft delete, not permanent.
    """
    process = _get_process_or_404(process_id, db)

    process.is_active = False
    db.commit()

    logger.info(f"Deactivated process: {process_id}")

    return success_response(
        data=ProcessDeactivateData(process_id=process_id),
        message="Process deactivated successfully",
    )
