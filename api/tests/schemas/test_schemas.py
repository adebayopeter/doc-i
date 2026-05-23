"""
Tests for Pydantic schemas — validation and serialisation.
"""
import pytest
from pydantic import ValidationError

from schemas.process import ProcessCreate, ProcessDocumentIn
from schemas.submission import SubmissionCreate
from schemas.base import success_response, error_response


# ── ProcessCreate ──────────────────────────────────────────────────────────

def test_process_create_valid():
    payload = ProcessCreate(
        name="RSA Mortgage",
        documents=[
            ProcessDocumentIn(name="NIN slip", category="Identity")
        ],
    )
    assert payload.name == "RSA Mortgage"
    assert len(payload.documents) == 1


def test_process_create_requires_name():
    with pytest.raises(ValidationError) as exc:
        ProcessCreate(documents=[
            ProcessDocumentIn(name="NIN slip", category="Identity")
        ])
    assert "name" in str(exc.value)


def test_process_create_requires_at_least_one_document():
    with pytest.raises(ValidationError):
        ProcessCreate(name="Test Process", documents=[])


def test_process_create_name_minimum_length():
    with pytest.raises(ValidationError):
        ProcessCreate(
            name="A",
            documents=[ProcessDocumentIn(name="NIN slip", category="Identity")]
        )


def test_process_document_defaults():
    doc = ProcessDocumentIn(name="NIN slip", category="Identity")
    assert doc.is_required is True


def test_process_document_required_can_be_false():
    doc = ProcessDocumentIn(
        name="Cover letter",
        category="Supporting",
        is_required=False,
    )
    assert doc.is_required is False


# ── SubmissionCreate ───────────────────────────────────────────────────────

def test_submission_create_valid():
    payload = SubmissionCreate(process_id="proc_abc123")
    assert payload.process_id == "proc_abc123"
    assert payload.reference is None
    assert payload.applicant_id is None


def test_submission_create_with_optional_fields():
    payload = SubmissionCreate(
        process_id="proc_abc123",
        reference="APP-2025-001",
        applicant_id="usr_emeka_obi",
    )
    assert payload.reference == "APP-2025-001"
    assert payload.applicant_id == "usr_emeka_obi"


def test_submission_create_requires_process_id():
    with pytest.raises(ValidationError):
        SubmissionCreate()


# ── Response helpers ───────────────────────────────────────────────────────

def test_success_response_structure():
    response = success_response(
        data={"process_id": "proc_abc123"},
        message="Process created successfully",
    )
    assert response["success"] is True
    assert response["message"] == "Process created successfully"
    assert response["data"]["process_id"] == "proc_abc123"


def test_success_response_default_message():
    response = success_response(data={"key": "value"})
    assert response["message"] == "Request successful"


def test_success_response_none_data():
    response = success_response()
    assert response["success"] is True
    assert response["data"] is None


def test_error_response_structure():
    response = error_response(message="Process not found")
    assert response["success"] is False
    assert response["message"] == "Process not found"
    assert response["data"] is None


def test_error_response_with_data():
    response = error_response(
        message="Validation failed",
        data={"field": "name", "error": "too short"},
    )
    assert response["data"]["field"] == "name"
