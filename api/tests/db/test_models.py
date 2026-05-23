"""
Tests for SQLAlchemy models.
"""

import pytest
from db.models import (
    AuditLog,
    Process,
    ProcessDocument,
    Submission,
    SubmissionDocument,
    ValidationRule,
)

# ── Process ────────────────────────────────────────────────────────────────


def test_process_creates_successfully(db_session):
    process = Process(name="RSA Mortgage", description="Test process")
    db_session.add(process)
    db_session.commit()

    assert process.id is not None
    assert process.id.startswith("proc_")
    assert process.name == "RSA Mortgage"
    assert process.is_active is True


def test_process_id_has_correct_prefix(db_session):
    process = Process(name="Benefits Application")
    db_session.add(process)
    db_session.commit()
    assert process.id.startswith("proc_")


def test_process_defaults(db_session):
    process = Process(name="Test Process")
    db_session.add(process)
    db_session.commit()

    assert process.is_active is True
    assert process.color_var == "info"
    assert process.icon == "ti-file"
    assert process.description is None


def test_process_name_is_required(db_session):
    with pytest.raises(Exception):
        process = Process()
        db_session.add(process)
        db_session.commit()


def test_process_with_documents(db_session):
    process = Process(name="KYC Process")
    db_session.add(process)
    db_session.flush()

    doc = ProcessDocument(
        process_id=process.id,
        name="National ID",
        category="Identity",
        sort_order=0,
    )
    db_session.add(doc)
    db_session.commit()

    assert len(process.documents) == 1
    assert process.documents[0].name == "National ID"


def test_process_document_cascades_on_delete(db_session):
    process = Process(name="Cascade Test")
    db_session.add(process)
    db_session.flush()

    doc = ProcessDocument(
        process_id=process.id,
        name="Test Doc",
        category="Identity",
    )
    db_session.add(doc)
    db_session.commit()

    db_session.delete(process)
    db_session.commit()

    remaining = db_session.query(ProcessDocument).filter_by(process_id=process.id).all()
    assert len(remaining) == 0


# ── Submission ─────────────────────────────────────────────────────────────


def test_submission_creates_successfully(db_session):
    process = Process(name="Test Process")
    db_session.add(process)
    db_session.flush()

    submission = Submission(
        process_id=process.id,
        reference="APP-2025-001",
    )
    db_session.add(submission)
    db_session.commit()

    assert submission.id.startswith("sub_")
    assert submission.status == "open"
    assert submission.reference == "APP-2025-001"


def test_submission_default_status(db_session):
    process = Process(name="Test Process")
    db_session.add(process)
    db_session.flush()

    submission = Submission(process_id=process.id)
    db_session.add(submission)
    db_session.commit()

    assert submission.status == "open"


# ── SubmissionDocument ─────────────────────────────────────────────────────


def test_submission_document_creates_successfully(db_session):
    process = Process(name="Test Process")
    db_session.add(process)
    db_session.flush()

    submission = Submission(process_id=process.id)
    db_session.add(submission)
    db_session.flush()

    doc = SubmissionDocument(
        submission_id=submission.id,
        filename="nin_slip.pdf",
        mime_type="application/pdf",
    )
    db_session.add(doc)
    db_session.commit()

    assert doc.id.startswith("doc_")
    assert doc.status == "uploaded"
    assert doc.filename == "nin_slip.pdf"


def test_submission_document_default_status(db_session):
    process = Process(name="Test Process")
    db_session.add(process)
    db_session.flush()

    submission = Submission(process_id=process.id)
    db_session.add(submission)
    db_session.flush()

    doc = SubmissionDocument(
        submission_id=submission.id,
        filename="test.pdf",
    )
    db_session.add(doc)
    db_session.commit()

    assert doc.status == "uploaded"
    assert doc.extracted_fields == {}
    assert doc.flags == []


# ── ValidationRule ─────────────────────────────────────────────────────────


def test_validation_rule_creates_successfully(db_session):
    rule = ValidationRule(
        name="Full name required",
        rule_type="required",
        field="Full Name",
        severity="error",
    )
    db_session.add(rule)
    db_session.commit()

    assert rule.id.startswith("rule_")
    assert rule.is_enabled is True
    assert rule.severity == "error"


# ── AuditLog ───────────────────────────────────────────────────────────────


def test_audit_log_creates_successfully(db_session):
    process = Process(name="Test Process")
    db_session.add(process)
    db_session.flush()

    submission = Submission(process_id=process.id)
    db_session.add(submission)
    db_session.flush()

    log = AuditLog(
        submission_id=submission.id,
        event="document.uploaded",
        actor="system",
        payload={"filename": "nin_slip.pdf"},
    )
    db_session.add(log)
    db_session.commit()

    assert log.id is not None
    assert log.event == "document.uploaded"
    assert log.payload["filename"] == "nin_slip.pdf"
