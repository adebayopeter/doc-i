"""
Documents router — /v1/documents

Handles document uploads within a submission.
Each upload triggers async AI classification via Celery.

Endpoints:
    POST   /v1/documents/submissions/{submission_id}/upload.
           Upload a document — returns immediately, classification runs async
    GET    /v1/documents/{document_id}
           Get a classified document with extracted fields
    DELETE /v1/documents/{document_id}
           Remove a document from a submission
"""

import uuid
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from config.dependencies import AuthContext, get_db, verify_api_key
from config.logging import get_logger
from db.models import Submission, SubmissionDocument
from schemas.base import error_response, success_response
from services.api_keys import verify_key_for_process

logger = get_logger(__name__)

# ── Module-level dependencies ──────────────────────────────────────────────
db_dependency = Depends(get_db)
auth_dependency = Depends(verify_api_key)

file_upload = (
    File(
        ...,
        description="Document file — PDF, PNG, JPG, WEBP or TIFF. Max 20MB.",
    ),
)

files_upload = File(
    ...,
    description="Up to 10 document files.",
)

# ── Allowed MIME types ─────────────────────────────────────────────────────
ALLOWED_MIME_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/tiff",
}

# Maximum file size — 20MB
MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024

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

_404_document = {
    "description": "Document not found",
    "content": {
        "application/json": {
            "example": {
                "success": False,
                "message": "Document not found",
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

_422_submission = {
    "description": "Submission is in a terminal state",
    "content": {
        "application/json": {
            "example": {
                "success": False,
                "message": (
                    "Cannot upload documents to a submission " "with status 'complete'"
                ),
                "data": None,
            },
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
    """Fetch an active submission by ID. Raises 404 if not found."""
    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if not submission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_response("Submission not found"),
        )
    return submission


def _get_document_or_404(document_id: str, db: Session) -> SubmissionDocument:
    """Fetch a document by ID. Raises 404 if not found."""
    document = (
        db.query(SubmissionDocument)
        .filter(SubmissionDocument.id == document_id)
        .first()
    )
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_response("Document not found"),
        )
    return document


def _build_document_out(document: SubmissionDocument) -> dict:
    """Build a document response dict from a SubmissionDocument ORM object."""
    extracted = None
    if document.extracted_fields:
        extracted = {
            field: {
                "value": data.get("value") if isinstance(data, dict) else data,
                "confidence": (
                    data.get("confidence", 0) if isinstance(data, dict) else 0
                ),
            }
            for field, data in document.extracted_fields.items()
        }

    flags = None
    if document.flags:
        flags = [
            {"type": f.get("type", "ok"), "message": f.get("message", "")}
            for f in document.flags
        ]

    return {
        "document_id": document.id,
        "submission_id": document.submission_id,
        "filename": document.filename,
        "mime_type": document.mime_type,
        "status": document.status,
        "document_type": document.document_type,
        "matched_doc_id": document.matched_doc_id,
        "overall_confidence": document.overall_confidence,
        "extracted_fields": extracted,
        "flags": flags,
        "summary": document.summary,
        "created_at": document.created_at.isoformat() if document.created_at else None,
        "updated_at": document.updated_at.isoformat() if document.updated_at else None,
    }


def _get_file_bytes_b64(document_id: str, db: Session) -> str | None:
    """Fetch file from MinIO and return as base64 for Celery task."""
    import base64

    from services.storage import get_file

    doc = (
        db.query(SubmissionDocument)
        .filter(SubmissionDocument.id == document_id)
        .first()
    )
    if not doc:
        return None
    try:
        file_bytes = get_file(doc.storage_path)
        return base64.b64encode(file_bytes).decode("utf-8")
    except Exception as e:
        logger.error(f"Could not fetch file for queuing: {e}")
        return None


def _store_file_locally(
    file_bytes: bytes,
    filename: str,
    submission_id: str,
) -> str:
    """
    Store file in MinIO and return the object key.
    Falls back to a local path reference if MinIO is not configured.
    The actual storage call happens in the Celery worker (services/storage.py).
    Here we just generate the object key for the DB record.
    """
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    object_key = f"{submission_id}/{uuid.uuid4().hex}.{ext}"
    return object_key


# ── POST /v1/documents/submissions/{submission_id}/upload ─────────────────
@router.post(
    "/submissions/{submission_id}/upload",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload a document",
    description=(
        "Uploads a document to a submission and immediately queues it for "
        "AI classification. Returns 202 Accepted — classification runs "
        "asynchronously in the background. \n\n"
        "Poll GET /v1/documents/{document_id} to check classification status.\n\n"
        "**Supported formats:** PDF, PNG, JPG, WEBP, TIFF\n\n"
        "**Maximum file size:** 20MB\n\n"
        "The AI reads the document, identifies the document type against the "
        "process checklist, and extracts key fields such as Full Name, NIN, "
        "Date of Birth, Address, and more — with a confidence score per field."
    ),
    response_description="Document uploaded and queued for classification",
    responses={
        202: {
            "description": "Document uploaded — classification running",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "message": (
                            "Document uploaded successfully. "
                            "Classification is running."
                        ),
                        "data": {
                            "document_id": "doc_r7tn4q12",
                            "submission_id": "sub_k9m2xp12",
                            "filename": "nin_slip.pdf",
                            "mime_type": "application/pdf",
                            "status": "processing",
                        },
                    }
                }
            },
        },
        400: {
            "description": "Invalid file type or file too large",
            "content": {
                "application/json": {
                    "examples": {
                        "invalid_type": {
                            "summary": "Unsupported file type",
                            "value": {
                                "success": False,
                                "message": (
                                    "Unsupported file type: text/plain. "
                                    "Allowed: PDF, PNG, JPG, WEBP, TIFF"
                                ),
                                "data": None,
                            },
                        },
                        "too_large": {
                            "summary": "File exceeds 20MB limit",
                            "value": {
                                "success": False,
                                "message": ("File too large. Maximum size is 20MB."),
                                "data": None,
                            },
                        },
                    }
                }
            },
        },
        404: _404_submission,
        422: _422_submission,
    },
)
async def upload_document(
    submission_id: str,
    file: UploadFile = file_upload,
    db: Session = db_dependency,
    auth: AuthContext = Depends(verify_api_key),
):
    # Verify submission exists
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

    # Block uploads to terminal submissions
    if submission.status in {"complete", "rejected"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=error_response(
                f"Cannot upload documents to a submission "
                f"with status '{submission.status}'"
            ),
        )

    # Validate MIME type
    mime_type = file.content_type or "application/octet-stream"
    if mime_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_response(
                f"Unsupported file type: {mime_type}. "
                f"Allowed: PDF, PNG, JPG, WEBP, TIFF"
            ),
        )

    # Read and validate file size
    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_response(
                f"File too large. Maximum size is 20MB. "
                f"Received: {len(file_bytes) / (1024 * 1024):.1f}MB"
            ),
        )

    if len(file_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_response("Uploaded file is empty"),
        )

    filename = file.filename or f"document_{uuid.uuid4().hex}"

    # Generate storage path — actual upload happens in the Celery worker
    storage_path = _store_file_locally(file_bytes, filename, submission_id)

    # Create the document record
    document = SubmissionDocument(
        submission_id=submission_id,
        filename=filename,
        storage_path=storage_path,
        mime_type=mime_type,
        status="uploaded",
        extracted_fields={},
        flags=[],
    )
    db.add(document)

    # Update submission status to in_progress if still open
    if submission.status == "open":
        submission.status = "in_progress"

    db.commit()
    db.refresh(document)

    logger.info(
        f"Document uploaded: {document.id} "
        f"({filename}, {len(file_bytes)} bytes) "
        f"for submission: {submission_id}"
    )

    # Queue async classification task
    # The worker calls Azure DocInt (OCR) then Claude (extraction)
    try:
        import base64

        from workers.tasks import process_document

        file_bytes_b64 = base64.b64encode(file_bytes).decode()
        process_document.delay(document.id, submission_id, file_bytes_b64)
        logger.info(f"Classification queued for document: {document.id}")
    except Exception as e:
        # Do not fail the upload if the queue is unavailable
        # The document stays in 'uploaded' status and can be requeued
        logger.warning(
            f"Could not queue classification for {document.id}: {e}. "
            f"Document saved — classification can be retried."
        )

    return success_response(
        data={
            "document_id": document.id,
            "submission_id": submission_id,
            "filename": document.filename,
            "mime_type": document.mime_type,
            "status": document.status,
        },
        message="Document uploaded successfully. Classification is running.",
    )


# ── GET /v1/documents/{document_id} ───────────────────────────────────────
@router.get(
    "/{document_id}",
    summary="Get a document",
    description=(
        "Returns a document with its current classification status and "
        "all extracted fields. \n\n"
        "**Status values:**\n"
        "- `uploaded` — received, awaiting classification\n"
        "- `processing` — AI classification is running\n"
        "- `classified` — complete, extracted fields available\n"
        "- `failed` — classification failed, check flags\n\n"
        "Poll this endpoint after uploading until status is `classified` or `failed`. "
        "Typically takes 3–8 seconds depending on document complexity."
    ),
    response_description="Document retrieved successfully",
    responses={
        200: {
            "description": "Document retrieved successfully",
            "content": {
                "application/json": {
                    "examples": {
                        "classified": {
                            "summary": "Document classified — fields extracted",
                            "value": {
                                "success": True,
                                "message": "Document retrieved successfully",
                                "data": {
                                    "document_id": "doc_r7tn4q12",
                                    "submission_id": "sub_k9m2xp12",
                                    "filename": "nin_slip.pdf",
                                    "mime_type": "application/pdf",
                                    "status": "classified",
                                    "document_type": "National ID / NIN slip",
                                    "matched_doc_id": 1,
                                    "overall_confidence": 91.5,
                                    "extracted_fields": {
                                        "Full Name": {
                                            "value": "Emeka Obi",
                                            "confidence": 94,
                                        },
                                        "NIN": {
                                            "value": "12345678901",
                                            "confidence": 97,
                                        },
                                        "Date of Birth": {
                                            "value": "1990-03-15",
                                            "confidence": 89,
                                        },
                                        "Address": {
                                            "value": (
                                                "12 Adeola Odeku Street, "
                                                "Victoria Island, Lagos"
                                            ),
                                            "confidence": 82,
                                        },
                                    },
                                    "flags": [
                                        {
                                            "type": "ok",
                                            "message": (
                                                "Document valid and not expired"
                                            ),
                                        }
                                    ],
                                    "summary": (
                                        "Valid NIN slip issued by NIMC. "
                                        "All fields clearly legible."
                                    ),
                                    "created_at": "2025-05-20T10:20:00Z",
                                    "updated_at": "2025-05-20T10:20:45Z",
                                },
                            },
                        },
                        "processing": {
                            "summary": "Document still being classified",
                            "value": {
                                "success": True,
                                "message": "Document retrieved successfully",
                                "data": {
                                    "document_id": "doc_r7tn4q12",
                                    "submission_id": "sub_k9m2xp12",
                                    "filename": "nin_slip.pdf",
                                    "mime_type": "application/pdf",
                                    "status": "processing",
                                    "document_type": None,
                                    "matched_doc_id": None,
                                    "overall_confidence": None,
                                    "extracted_fields": None,
                                    "flags": None,
                                    "summary": None,
                                    "created_at": "2025-05-20T10:20:00Z",
                                    "updated_at": "2025-05-20T10:20:00Z",
                                },
                            },
                        },
                        "failed": {
                            "summary": "Classification failed",
                            "value": {
                                "success": True,
                                "message": "Document retrieved successfully",
                                "data": {
                                    "document_id": "doc_r7tn4q12",
                                    "submission_id": "sub_k9m2xp12",
                                    "filename": "blurry_scan.jpg",
                                    "mime_type": "image/jpeg",
                                    "status": "failed",
                                    "document_type": None,
                                    "matched_doc_id": None,
                                    "overall_confidence": None,
                                    "extracted_fields": None,
                                    "flags": [
                                        {
                                            "type": "err",
                                            "message": (
                                                "Image quality too low for "
                                                "reliable extraction. "
                                                "Please upload a clearer scan."
                                            ),
                                        }
                                    ],
                                    "summary": None,
                                    "created_at": "2025-05-20T10:20:00Z",
                                    "updated_at": "2025-05-20T10:20:30Z",
                                },
                            },
                        },
                    }
                }
            },
        },
        404: _404_document,
    },
)
def get_document(
    document_id: str,
    db: Session = db_dependency,
    auth: AuthContext = Depends(verify_api_key),
):
    document = _get_document_or_404(document_id, db)

    # Look up the submission to check process access
    submission = _get_submission_or_404(document.submission_id, db)
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

    logger.info(f"Retrieved document: {document_id} status={document.status}")

    return success_response(
        data=_build_document_out(document),
        message="Document retrieved successfully",
    )


# ── DELETE /v1/documents/{document_id} ────────────────────────────────────
@router.delete(
    "/{document_id}",
    status_code=status.HTTP_200_OK,
    summary="Remove a document",
    description=(
        "Removes a document from a submission. "
        "The document record and its extracted data are deleted from the database. "
        "The raw file is also removed from storage.\n\n"
        "Cannot remove documents from submissions with status `complete` or `rejected`."
    ),
    response_description="Document removed successfully",
    responses={
        200: {
            "description": "Document removed successfully",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "message": "Document removed successfully",
                        "data": {
                            "document_id": "doc_r7tn4q12",
                            "submission_id": "sub_k9m2xp12",
                        },
                    }
                }
            },
        },
        404: _404_document,
        422: _422_submission,
    },
)
def delete_document(
    document_id: str,
    db: Session = db_dependency,
    auth: AuthContext = Depends(verify_api_key),
):
    document = _get_document_or_404(document_id, db)
    submission = _get_submission_or_404(document.submission_id, db)

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

    # Block deletion from terminal submissions
    if submission.status in {"complete", "rejected"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=error_response(
                f"Cannot remove documents from a submission "
                f"with status '{submission.status}'"
            ),
        )

    submission_id = document.submission_id

    # Remove file from storage
    if document.storage_path:
        try:
            from services.storage import delete_file

            delete_file(document.storage_path)
        except Exception as e:
            logger.warning(
                f"Could not delete file from storage " f"{document.storage_path}: {e}"
            )

    db.delete(document)
    db.commit()

    logger.info(f"Document removed: {document_id} from submission: {submission_id}")

    return success_response(
        data={
            "document_id": document_id,
            "submission_id": submission_id,
        },
        message="Document removed successfully",
    )


@router.post(
    "/submissions/{submission_id}/upload-bulk",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload multiple documents",
    description=(
        "Upload up to 10 documents in a single request. "
        "Each file is stored and queued for classification independently. "
        "Returns a list of document IDs and their upload status."
    ),
    responses={
        202: {
            "description": "All files accepted for processing",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "message": "3 documents uploaded successfully",
                        "data": {
                            "submission_id": "sub_1a2b3c4d5e6f",
                            "uploaded": [
                                {
                                    "document_id": "doc_1a2b3c4d5e6f",
                                    "filename": "nin_slip.pdf",
                                    "status": "uploaded",
                                },
                                {
                                    "document_id": "doc_2b3c4d5e6f7a",
                                    "filename": "bank_statement.pdf",
                                    "status": "uploaded",
                                },
                            ],
                            "failed": [],
                            "total_uploaded": 2,
                            "total_failed": 0,
                        },
                    }
                }
            },
        },
        404: _404_submission,
        422: _422_submission,
    },
)
def upload_bulk_documents(
    submission_id: str,
    files: List[UploadFile] = files_upload,
    db: Session = db_dependency,
    auth: AuthContext = Depends(verify_api_key),
):
    from services.storage import upload_file
    from workers.tasks import process_document

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

    if submission.status == "complete":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=error_response("Cannot upload to a completed submission"),
        )
    if submission.status == "rejected":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=error_response("Cannot upload to a rejected submission"),
        )

    if len(files) > 10:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=error_response("Maximum 10 files per bulk upload request"),
        )

    uploaded = []
    failed = []

    for file in files:
        try:
            # Validate file
            if file.content_type not in ALLOWED_MIME_TYPES:
                failed.append(
                    {
                        "filename": file.filename,
                        "reason": f"Unsupported file type: {file.content_type}",
                    }
                )
                continue

            contents = file.file.read()
            if len(contents) == 0:
                failed.append({"filename": file.filename, "reason": "Empty file"})
                continue

            # Store in MinIO
            storage_path = upload_file(
                file_bytes=contents,
                filename=file.filename,
                mime_type=file.content_type,
                submission_id=submission_id,
            )

            # Create DB record
            doc = SubmissionDocument(
                submission_id=submission_id,
                filename=file.filename,
                storage_path=storage_path,
                mime_type=file.content_type,
                status="uploaded",
            )
            db.add(doc)
            db.flush()

            uploaded.append(
                {
                    "document_id": doc.id,
                    "filename": file.filename,
                    "status": "uploaded",
                }
            )

            logger.info(
                f"Bulk upload: {doc.id} ({file.filename}) "
                f"for submission {submission_id}"
            )

        except Exception as e:
            logger.error(f"Bulk upload failed for {file.filename}: {e}")
            failed.append({"filename": file.filename, "reason": str(e)})

    # Move submission to in_progress if any uploaded
    if uploaded and submission.status == "open":
        submission.status = "in_progress"

    db.commit()

    # Queue classification for all uploaded docs
    for doc_info in uploaded:
        file_bytes_b64 = _get_file_bytes_b64(doc_info["document_id"], db)
        if file_bytes_b64:
            process_document.delay(
                doc_info["document_id"],
                submission_id,
                file_bytes_b64,
            )

    total_uploaded = len(uploaded)
    total_failed = len(failed)

    logger.info(
        f"Bulk upload complete: {total_uploaded} uploaded, "
        f"{total_failed} failed for submission {submission_id}"
    )

    return success_response(
        data={
            "submission_id": submission_id,
            "uploaded": uploaded,
            "failed": failed,
            "total_uploaded": total_uploaded,
            "total_failed": total_failed,
        },
        message=f"{total_uploaded} document(s) uploaded successfully",
    )
