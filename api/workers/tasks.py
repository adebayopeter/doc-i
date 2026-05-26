"""
Celery worker tasks.

process_document — the only task.
Picks up a document_id from the Redis queue,
runs OCR via Azure DocInt, then classification via Claude,
and saves results back to PostgreSQL.
"""

from celery import Celery

from config.settings import settings

celery_app = Celery(
    "doc_intelligence",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    broker_connection_retry_on_startup=True,
)


@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,  # wait 30s before retrying
    name="workers.tasks.process_document",
)
def process_document(
    self,
    document_id: str,
    submission_id: str,
    file_bytes_b64: str,
) -> dict:
    """
    Main processing task — runs in the Celery worker.

    Pipeline:
      1. Load document and mark as processing
      2. Store file in MinIO
      3. OCR via Azure DocInt (extract raw text)
      4. Load process extraction fields — abort if none configured
      5. Classify + extract via Claude using configured fields only
      6. Persist results to DB

    Args:
        document_id:    SubmissionDocument.id to update
        submission_id:  Parent Submission.id
        file_bytes_b64: Base64-encoded file bytes

    Returns:
        Dict with status and documentType on success.

    Raises:
        Retries up to 3 times on any exception with 30s delay.
        On permanent failure, document status is set to 'failed'.
    """
    import base64

    from config.logging import get_logger
    from db.models import (
        Process,
        ProcessExtractionField,
        Submission,
        SubmissionDocument,
    )
    from db.session import SessionLocal
    from services.extraction import classify_and_extract
    from services.ocr import extract_text
    from services.storage import upload_file

    logger = get_logger(__name__)
    db = SessionLocal()

    try:
        # ── 1. Load document record ───────────────────────────────────────────
        doc = (
            db.query(SubmissionDocument)
            .filter(SubmissionDocument.id == document_id)
            .first()
        )
        if not doc:
            logger.error(f"Document not found: {document_id}")
            return {"status": "error", "message": "Document not found"}

        # Mark as processing
        doc.status = "processing"
        db.commit()
        logger.info(f"Processing document: {document_id} ({doc.filename})")

        # ── 2. Decode file bytes ──────────────────────────────────────────────
        file_bytes = base64.b64decode(file_bytes_b64)

        # ── 3. Store file in MinIO ────────────────────────────────────────────
        try:
            storage_path = upload_file(
                file_bytes=file_bytes,
                filename=doc.filename,
                mime_type=doc.mime_type or "application/octet-stream",
                submission_id=submission_id,
            )
            doc.storage_path = storage_path
            db.commit()
        except Exception as e:
            logger.warning(f"MinIO upload failed for {document_id}: {e}")
            # Continue processing even if storage fails

        # ── 4. OCR — extract raw text via Azure DocInt ───────────────
        ocr_text = extract_text(
            file_bytes=file_bytes,
            mime_type=doc.mime_type or "application/pdf",
        )

        # ── 5. Load process and checklist ──────────────────────────────────
        submission = db.query(Submission).filter(Submission.id == submission_id).first()
        process = db.query(Process).filter(Process.id == submission.process_id).first()
        checklist = [
            {
                "id": d.id,
                "name": d.name,
                "category": d.category,
            }
            for d in sorted(process.documents, key=lambda x: x.sort_order)
        ]

        # ── 6. Load extraction fields — STRICT no-fallback ─────────────────
        extraction_fields_raw = (
            db.query(ProcessExtractionField)
            .filter(
                ProcessExtractionField.process_id == submission.process_id,
                ProcessExtractionField.is_active.is_(True),
            )
            .order_by(ProcessExtractionField.sort_order.asc())
            .all()
        )

        # No active fields = extraction disabled for this process
        if not extraction_fields_raw:
            logger.warning(
                f"Process {submission.process_id} has no active extraction "
                f"fields — classification disabled for {document_id}"
            )
            doc.status = "failed"
            doc.flags = [
                {
                    "type": "err",
                    "message": (
                        "Extraction is disabled for this process. "
                        "Go to the process settings and configure "
                        "extraction fields before uploading documents."
                    ),
                }
            ]
            db.commit()
            return {
                "status": "error",
                "message": "No extraction fields configured",
            }

        extraction_fields = [
            {
                "name": f.name,
                "include_in_decision": f.include_in_decision,
                "null_is_manual": f.null_is_manual,
            }
            for f in extraction_fields_raw
        ]

        logger.info(
            f"Extraction fields loaded: {len(extraction_fields)} fields "
            f"for process {submission.process_id}"
        )

        # ── 7. Classify + extract via Claude ──────────────────────────
        result = classify_and_extract(
            process_name=process.name,
            document_checklist=checklist,
            extraction_fields=extraction_fields,
            ocr_text=ocr_text,
            file_bytes=file_bytes if not ocr_text else b"",
            mime_type=doc.mime_type or "" if not ocr_text else "",
        )

        # ── 8. Persist classification results ─────────────────────────
        doc.status = "classified"
        doc.document_type = result.get("documentType")
        doc.matched_doc_id = result.get("matchedDocId")
        doc.overall_confidence = result.get("confidence")
        doc.extracted_fields = result.get("extractedFields", {})
        doc.flags = result.get("flags", [])
        doc.summary = result.get("summary")
        doc.raw_ocr_text = ocr_text

        db.commit()
        db.refresh(doc)

        logger.info(
            f"Document classified: {document_id} → "
            f"'{doc.document_type}' ({doc.overall_confidence}%)"
        )

        return {
            "status": "classified",
            "documentType": doc.document_type,
            "confidence": doc.overall_confidence,
        }

    except Exception as exc:
        logger.error(f"Classification failed for {document_id}: {exc}")

        # Mark as failed on final retry
        if self.request.retries >= self.max_retries:
            try:
                doc = (
                    db.query(SubmissionDocument)
                    .filter(SubmissionDocument.id == document_id)
                    .first()
                )
                if doc:
                    doc.status = "failed"
                    doc.flags = [
                        {
                            "type": "err",
                            "message": (
                                f"Classification failed after "
                                f"{self.max_retries} attempts: {str(exc)}"
                            ),
                        }
                    ]
                    db.commit()
            except Exception as db_error:
                logger.error(f"Could not update failed status: {db_error}")

        raise self.retry(exc=exc, countdown=30)

    finally:
        db.close()
