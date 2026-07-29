"""
Submissions router — /v1/submissions

A submission is one application case for one applicant under a process.
All uploaded documents belong to a submission.

Endpoints:
    POST  /v1/submissions                         Open a new submission
    GET   /v1/submissions                         List all submissions
    GET   /v1/submissions/{submission_id}         Get a submission with progress
    GET   /v1/submissions/{submission_id}/documents List documents in a submission
    PATCH /v1/submissions/{submission_id}/status  Update submission status
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from config.dependencies import AuthContext, get_db, verify_api_key
from config.logging import get_logger
from db.models import Process, Submission, SubmissionDocument
from schemas.base import error_response, success_response
from schemas.submission import (
    SubmissionCreate,
    SubmissionListData,
    SubmissionOut,
    SubmissionProgress,
)
from services.api_keys import verify_key_for_process

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

_422 = {
    "description": "Validation error — request body failed schema validation",
    "content": {
        "application/json": {
            "example": {
                "success": False,
                "message": "process_id: field required",
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

# ── Allowed status transitions ─────────────────────────────────────────────
# Defines which status values are valid and which transitions are allowed.
# Prevents invalid state changes e.g. reopening a rejected submission.
VALID_STATUSES = {"open", "in_progress", "complete", "rejected"}

STATUS_TRANSITIONS = {
    "open": {"in_progress", "rejected"},
    "in_progress": {"complete", "rejected"},
    "complete": set(),  # terminal state — no further transitions
    "rejected": set(),  # terminal state — no further transitions
}

router = APIRouter(
    dependencies=[auth_dependency],
    responses={401: _401, 500: _500},
)


# ── Helpers ────────────────────────────────────────────────────────────────
def _get_submission_or_404(submission_id: str, db: Session) -> Submission:
    """Fetch a submission by ID. Raises 404 if not found."""
    submission = (
        db.query(Submission)
        .options(
            joinedload(Submission.process).joinedload(Process.documents),
            joinedload(Submission.documents),
        )
        .filter(Submission.id == submission_id)
        .first()
    )
    if not submission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_response("Submission not found"),
        )
    return submission


def _build_submission_out(submission: Submission) -> SubmissionOut:
    """Build a SubmissionOut from a Submission ORM object."""
    classified = len([d for d in submission.documents if d.status == "classified"])
    required = len(submission.process.documents) if submission.process else 0
    process_name = submission.process.name if submission.process else ""

    return SubmissionOut(
        submission_id=submission.id,
        process_id=submission.process_id,
        process_name=process_name,
        reference=submission.reference,
        applicant_id=submission.applicant_id,
        status=submission.status,
        progress=SubmissionProgress(
            classified=classified,
            required=required,
        ),
        documents_uploaded=len(submission.documents),
        created_at=submission.created_at,
        updated_at=submission.updated_at,
    )


def _build_submission_out_with_process(
    submission: Submission,
    process: Process,
) -> SubmissionOut:
    """
    Build a SubmissionOut using an explicitly provided process.
    Used in create_submission where the process is already fetched
    and the relationship may not be loaded on the fresh submission.
    """
    classified = len([d for d in submission.documents if d.status == "classified"])
    return SubmissionOut(
        submission_id=submission.id,
        process_id=submission.process_id,
        process_name=process.name,
        reference=submission.reference,
        applicant_id=submission.applicant_id,
        status=submission.status,
        progress=SubmissionProgress(
            classified=classified,
            required=len(process.documents),
        ),
        documents_uploaded=len(submission.documents),
        created_at=submission.created_at,
        updated_at=submission.updated_at,
    )


# ── POST /v1/submissions ───────────────────────────────────────────────────
@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Open a new submission",
    description=(
        "Opens a new application case for an applicant under a given process. "
        "Every document upload is scoped to a submission — the submission ID "
        "must be passed when uploading documents. "
        "A single applicant can have multiple submissions under different processes. "
        "Status starts as 'open' and progresses through: "
        "open → in_progress → complete | rejected."
    ),
    response_description="Submission opened successfully",
    responses={
        201: {
            "description": "Submission opened successfully",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "message": "Submission opened successfully",
                        "data": {
                            "submission_id": "sub_k9m2xp12",
                            "process_id": "proc_a1b2c3d4e5f6",
                            "process_name": "RSA Mortgage",
                            "reference": "APP-2025-001",
                            "applicant_id": "usr_emeka_obi",
                            "status": "open",
                            "progress": {
                                "classified": 0,
                                "required": 22,
                            },
                            "documents_uploaded": 0,
                            "created_at": "2025-05-20T10:15:00Z",
                            "updated_at": "2025-05-20T10:15:00Z",
                        },
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
        422: _422,
    },
)
def create_submission(
    payload: SubmissionCreate,
    db: Session = db_dependency,
    auth: AuthContext = Depends(verify_api_key),
):
    logger.info(
        f"Opening submission for process: {payload.process_id} "
        f"ref: {payload.reference}"
    )

    # Check process access
    if not verify_key_for_process(auth.process_ids, payload.process_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "success": False,
                "message": (
                    f"This API key does not have access to "
                    f"process '{payload.process_id}'"
                ),
                "data": None,
            },
        )

    # Verify the process exists and is active
    process = (
        db.query(Process)
        .filter(
            Process.id == payload.process_id,
            Process.is_active.is_(True),  # noqa: E712
        )
        .first()
    )
    if not process:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_response(
                "Process not found — ensure the process_id is valid "
                "and the process is active"
            ),
        )

    submission = Submission(
        process_id=payload.process_id,
        reference=payload.reference,
        applicant_id=payload.applicant_id,
        status="open",
        meta_data={},
    )
    db.add(submission)
    db.commit()
    db.refresh(submission)

    logger.info(f"Submission opened: {submission.id}")

    return success_response(
        data=_build_submission_out_with_process(submission, process),
        message="Submission opened successfully",
    )


# ── GET /v1/submissions ────────────────────────────────────────────────────


@router.get(
    "",
    summary="List all submissions",
    description=(
        "Returns all submissions across all processes, ordered by most recent first. "
        "Each item includes the current status and document classification progress. "
        "Filter by process using the optional `process_id` query parameter."
    ),
    response_description="Submissions retrieved successfully",
    responses={
        200: {
            "description": "Submissions retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "message": "Submissions retrieved successfully",
                        "data": {
                            "items": [
                                {
                                    "submission_id": "sub_k9m2xp12",
                                    "process_id": "proc_a1b2c3d4e5f6",
                                    "process_name": "RSA Mortgage",
                                    "reference": "APP-2025-001",
                                    "applicant_id": "usr_emeka_obi",
                                    "status": "in_progress",
                                    "progress": {
                                        "classified": 14,
                                        "required": 22,
                                    },
                                    "documents_uploaded": 14,
                                    "created_at": "2025-05-20T10:15:00Z",
                                    "updated_at": "2025-05-20T14:30:00Z",
                                },
                                {
                                    "submission_id": "sub_m3n4op56",
                                    "process_id": "proc_b2c3d4e5f6a1",
                                    "process_name": "Benefit Application",
                                    "reference": "BEN-2025-042",
                                    "applicant_id": "usr_chisom_adaobi",
                                    "status": "complete",
                                    "progress": {
                                        "classified": 10,
                                        "required": 10,
                                    },
                                    "documents_uploaded": 10,
                                    "created_at": "2025-05-19T09:00:00Z",
                                    "updated_at": "2025-05-19T16:45:00Z",
                                },
                            ],
                            "total": 2,
                        },
                    }
                }
            },
        },
    },
)
def list_submissions(
    process_id: Optional[str] = None,
    db: Session = db_dependency,
    auth: AuthContext = Depends(verify_api_key),
):
    query = db.query(Submission).options(
        joinedload(Submission.process).joinedload(Process.documents),
        joinedload(Submission.documents),
    )

    # Filter by specific process if requested
    if process_id:
        # Check access to the requested process
        if not verify_key_for_process(auth.process_ids, process_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "success": False,
                    "message": (
                        f"This API key does not have access to "
                        f"process '{process_id}'"
                    ),
                    "data": None,
                },
            )
        query = query.filter(Submission.process_id == process_id)
    elif not auth.is_admin and auth.process_ids:
        # Non-admin keys only see submissions for their accessible processes
        query = query.filter(Submission.process_id.in_(auth.process_ids))

    submissions = query.order_by(Submission.created_at.desc()).all()

    logger.info(f"Listed {len(submissions)} submissions for key {auth.key_id}")

    return success_response(
        data=SubmissionListData(
            items=[_build_submission_out(s) for s in submissions],
            total=len(submissions),
        ),
        message="Submissions retrieved successfully",
    )


# ── GET /v1/submissions/{submission_id} ───────────────────────────────────


@router.get(
    "/{submission_id}",
    summary="Get a submission",
    description=(
        "Returns full submission details including current status, "
        "document classification progress, and applicant reference. "
        "Poll this endpoint after uploading documents to track "
        "classification progress."
    ),
    response_description="Submission retrieved successfully",
    responses={
        200: {
            "description": "Submission retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "message": "Submission retrieved successfully",
                        "data": {
                            "submission_id": "sub_k9m2xp12",
                            "process_id": "proc_a1b2c3d4e5f6",
                            "process_name": "RSA Mortgage",
                            "reference": "APP-2025-001",
                            "applicant_id": "usr_emeka_obi",
                            "status": "in_progress",
                            "progress": {
                                "classified": 14,
                                "required": 22,
                            },
                            "documents_uploaded": 14,
                            "created_at": "2025-05-20T10:15:00Z",
                            "updated_at": "2025-05-20T14:30:00Z",
                        },
                    }
                }
            },
        },
        404: _404_submission,
    },
)
def get_submission(
    submission_id: str,
    db: Session = db_dependency,
    auth: AuthContext = Depends(verify_api_key),
):
    submission = _get_submission_or_404(submission_id, db)

    # Check process access
    if not verify_key_for_process(auth.process_ids, submission.process_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "success": False,
                "message": (
                    f"This API key does not have access to "
                    f"process '{submission.process_id}'"
                ),
                "data": None,
            },
        )

    logger.info(f"Retrieved submission: {submission_id}")

    return success_response(
        data=_build_submission_out(submission),
        message="Submission retrieved successfully",
    )


# ── GET /v1/submissions/{submission_id}/documents ─────────────────────────


@router.get(
    "/{submission_id}/documents",
    summary="List documents in a submission",
    description=(
        "Returns all documents uploaded to a submission with their "
        "classification status and confidence scores. "
        "Status values: uploaded | processing | classified | failed. "
        "Poll individual document IDs for full extracted field data."
    ),
    response_description="Documents retrieved successfully",
    responses={
        200: {
            "description": "Documents retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "message": "Documents retrieved successfully",
                        "data": {
                            "submission_id": "sub_k9m2xp12",
                            "documents": [
                                {
                                    "document_id": "doc_r7tn4q12",
                                    "filename": "nin_slip.pdf",
                                    "mime_type": "application/pdf",
                                    "status": "classified",
                                    "document_type": "National ID / NIN slip",
                                    "matched_doc_id": 1,
                                    "overall_confidence": 91.5,
                                    "created_at": "2025-05-20T10:20:00Z",
                                },
                                {
                                    "document_id": "doc_s8uv5r23",
                                    "filename": "bank_statement.pdf",
                                    "mime_type": "application/pdf",
                                    "status": "classified",
                                    "document_type": "Bank statement (6 months)",
                                    "matched_doc_id": 2,
                                    "overall_confidence": 87.0,
                                    "created_at": "2025-05-20T10:25:00Z",
                                },
                                {
                                    "document_id": "doc_t9wx6s34",
                                    "filename": "offer_letter.jpg",
                                    "mime_type": "image/jpeg",
                                    "status": "processing",
                                    "document_type": None,
                                    "matched_doc_id": None,
                                    "overall_confidence": None,
                                    "created_at": "2025-05-20T10:30:00Z",
                                },
                            ],
                            "total": 3,
                            "classified": 2,
                            "processing": 1,
                            "failed": 0,
                        },
                    }
                }
            },
        },
        404: _404_submission,
    },
)
def list_submission_documents(
    submission_id: str,
    db: Session = db_dependency,
    auth: AuthContext = Depends(verify_api_key),
):
    submission = _get_submission_or_404(submission_id, db)

    # Check process access
    if not verify_key_for_process(auth.process_ids, submission.process_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "success": False,
                "message": (
                    f"This API key does not have access to "
                    f"process '{submission.process_id}'"
                ),
                "data": None,
            },
        )

    documents = (
        db.query(SubmissionDocument)
        .filter(SubmissionDocument.submission_id == submission_id)
        .order_by(SubmissionDocument.created_at.asc())
        .all()
    )

    logger.info(f"Listed {len(documents)} documents for submission: {submission_id}")

    classified = len([d for d in documents if d.status == "classified"])
    processing = len([d for d in documents if d.status == "processing"])
    failed = len([d for d in documents if d.status == "failed"])

    return success_response(
        data={
            "submission_id": submission_id,
            "documents": [
                {
                    "document_id": d.id,
                    "filename": d.filename,
                    "mime_type": d.mime_type,
                    "status": d.status,
                    "document_type": d.document_type,
                    "matched_doc_id": d.matched_doc_id,
                    "overall_confidence": d.overall_confidence,
                    "created_at": d.created_at,
                }
                for d in documents
            ],
            "total": len(documents),
            "classified": classified,
            "processing": processing,
            "failed": failed,
        },
        message="Documents retrieved successfully",
    )


# ── PATCH /v1/submissions/{submission_id}/status ──────────────────────────


@router.patch(
    "/{submission_id}/status",
    summary="Update submission status",
    description=(
        "Updates the status of a submission. "
        "Only valid transitions are allowed:\n\n"
        "- `open` → `in_progress` or `rejected`\n"
        "- `in_progress` → `complete` or `rejected`\n"
        "- `complete` → no further transitions (terminal)\n"
        "- `rejected` → no further transitions (terminal)\n\n"
        "Attempting an invalid transition returns 422."
    ),
    response_description="Submission status updated successfully",
    responses={
        200: {
            "description": "Status updated successfully",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "message": "Submission status updated to 'complete'",
                        "data": {
                            "submission_id": "sub_k9m2xp12",
                            "previous_status": "in_progress",
                            "new_status": "complete",
                        },
                    }
                }
            },
        },
        404: _404_submission,
        422: {
            "description": "Invalid status or transition not allowed",
            "content": {
                "application/json": {
                    "examples": {
                        "invalid_status": {
                            "summary": "Status value not recognised",
                            "value": {
                                "success": False,
                                "message": (
                                    "Invalid status 'archived'. "
                                    "Must be one of: open, in_progress, "
                                    "complete, rejected"
                                ),
                                "data": None,
                            },
                        },
                        "invalid_transition": {
                            "summary": "Transition not allowed",
                            "value": {
                                "success": False,
                                "message": (
                                    "Cannot transition from 'complete' "
                                    "to 'in_progress'"
                                ),
                                "data": {
                                    "current_status": "complete",
                                    "requested_status": "in_progress",
                                    "allowed_transitions": [],
                                },
                            },
                        },
                    }
                }
            },
        },
    },
)
def update_submission_status(
    submission_id: str,
    new_status: str,
    db: Session = db_dependency,
    auth: AuthContext = Depends(verify_api_key),
):
    submission = _get_submission_or_404(submission_id, db)

    # Check process access
    if not verify_key_for_process(auth.process_ids, submission.process_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "success": False,
                "message": (
                    f"This API key does not have access to "
                    f"process '{submission.process_id}'"
                ),
                "data": None,
            },
        )

    # Validate the requested status value
    if new_status not in VALID_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=error_response(
                f"Invalid status '{new_status}'. "
                f"Must be one of: {', '.join(sorted(VALID_STATUSES))}"
            ),
        )

    # Validate the transition
    allowed = STATUS_TRANSITIONS.get(submission.status, set())
    if new_status not in allowed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=error_response(
                f"Cannot transition from '{submission.status}' to '{new_status}'",
                data={
                    "current_status": submission.status,
                    "requested_status": new_status,
                    "allowed_transitions": sorted(allowed),
                },
            ),
        )

    previous_status = submission.status
    submission.status = new_status
    db.commit()

    logger.info(
        f"Submission {submission_id} status: " f"{previous_status} → {new_status}"
    )

    return success_response(
        data={
            "submission_id": submission_id,
            "previous_status": previous_status,
            "new_status": new_status,
        },
        message=f"Submission status updated to '{new_status}'",
    )
