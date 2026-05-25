"""
Celery tasks — async document processing pipeline.

Pipeline per document:
  1. Load file bytes from MinIO
  2. Extract raw text via Azure DocInt (OCR) — optional
  3. Classify + extract fields via Claude AI
  4. Persist results to PostgreSQL
  5. Update submission status

The upload endpoint returns 202 immediately.
This task runs in the background Celery worker container.
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
    result_expires=3600,
    worker_prefetch_multiplier=1,  # process one task at a time per worker
    task_acks_late=True,  # ack after completion — safer on failures
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

    Args:
        document_id:    SubmissionDocument.id to update
        submission_id:  Parent Submission.id
        file_bytes_b64: Base64-encoded file bytes

    Returns:
        Dict with status and documentType on success.

    The task retries up to 3 times with 30s delay on any exception.
    On permanent failure, document status is set to 'failed'.
    """
    import base64

    from config.logging import get_logger
    from db.models import Process, Submission, SubmissionDocument
    from db.session import SessionLocal
    from services.extraction import classify_and_extract
    from services.ocr import extract_text
    from services.storage import upload_file

    logger = get_logger(__name__)
    db = SessionLocal()

    try:
        # ── Load document record ───────────────────────────────────────────
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

        # ── Decode file bytes ──────────────────────────────────────────────
        file_bytes = base64.b64decode(file_bytes_b64)

        # ── Store file in MinIO ────────────────────────────────────────────
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

        # ── Step 1: OCR — extract raw text via Azure DocInt ───────────────
        ocr_text = extract_text(
            file_bytes=file_bytes,
            mime_type=doc.mime_type or "application/pdf",
        )

        # ── Step 2: Get process checklist ──────────────────────────────────
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

        # ── Step 3: Classify + extract via Claude ──────────────────────────
        result = classify_and_extract(
            process_name=process.name,
            document_checklist=checklist,
            ocr_text=ocr_text,
            file_bytes=file_bytes if not ocr_text else b"",
            mime_type=doc.mime_type or "" if not ocr_text else "",
        )

        # ── Step 4: Persist classification results ─────────────────────────
        doc.status = "classified"
        doc.document_type = result.get("documentType")
        doc.matched_doc_id = result.get("matchedDocId")
        doc.overall_confidence = result.get("confidence")
        doc.extracted_fields = result.get("extractedFields", {})
        doc.flags = result.get("flags", [])
        doc.summary = result.get("summary")
        doc.raw_ocr_text = ocr_text

        db.commit()

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
