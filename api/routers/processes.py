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
    ProcessDetail,
    ProcessDocumentOut,
    ProcessListData,
    ProcessSummary,
)

logger = get_logger(__name__)

db_dependency = Depends(get_db)
auth_dependency = Depends(verify_api_key)

router = APIRouter(
    dependencies=[auth_dependency],
    responses={
        401: {
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
        },
        404: {
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
        },
        500: {
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
        },
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
        data=_build_process_detail(process),
        message="Process created successfully",
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
        data=ProcessListData(
            items=[_build_process_summary(p) for p in processes],
            total=len(processes),
        ),
        message="Processes retrieved successfully",
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
        data=_build_process_detail(process),
        message="Process retrieved successfully",
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
        data={"process_id": process_id},
        message="Process deactivated successfully",
    )
