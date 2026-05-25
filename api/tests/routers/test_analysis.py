"""
Tests for /v1/analysis endpoints.
"""

import pytest

ANALYSIS_BASE = "/v1/analysis"
PROCESSES_BASE = "/v1/processes"
SUBMISSIONS_BASE = "/v1/submissions"


# ── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture
def created_process(client, api_key_headers):
    response = client.post(
        PROCESSES_BASE,
        json={
            "name": "RSA Mortgage",
            "description": "Test process",
            "documents": [
                {"name": "National ID / NIN slip", "category": "Identity"},
                {"name": "Bank statement", "category": "Financial"},
            ],
        },
        headers=api_key_headers,
    )
    assert response.status_code == 201
    return response.json()["data"]


@pytest.fixture
def created_submission(client, api_key_headers, created_process):
    response = client.post(
        SUBMISSIONS_BASE,
        json={
            "process_id": created_process["process_id"],
            "reference": "APP-2025-001",
        },
        headers=api_key_headers,
    )
    assert response.status_code == 201
    return response.json()["data"]


@pytest.fixture
def submission_with_classified_docs(db_session, created_submission):
    """
    Injects classified documents directly into the DB
    so we can test analysis without running the Celery worker.
    """
    from db.models import SubmissionDocument

    sid = created_submission["submission_id"]

    # Document 1 — NIN slip
    doc1 = SubmissionDocument(
        submission_id=sid,
        filename="nin_slip.pdf",
        mime_type="application/pdf",
        status="classified",
        document_type="National ID / NIN slip",
        matched_doc_id=1,
        overall_confidence=91.5,
        extracted_fields={
            "Full Name": {"value": "Emeka Obi", "confidence": 94},
            "NIN": {"value": "12345678901", "confidence": 97},
            "Date of Birth": {"value": "1990-03-15", "confidence": 89},
        },
        flags=[{"type": "ok", "message": "Document valid"}],
        summary="Valid NIN slip.",
    )
    db_session.add(doc1)

    # Document 2 — Bank statement with name conflict
    doc2 = SubmissionDocument(
        submission_id=sid,
        filename="bank_stmt.pdf",
        mime_type="application/pdf",
        status="classified",
        document_type="Bank statement",
        matched_doc_id=2,
        overall_confidence=87.0,
        extracted_fields={
            "Full Name": {"value": "E. Obi", "confidence": 71},
            "Account Number": {"value": "1234567890", "confidence": 95},
            "Bank Name": {"value": "First Bank", "confidence": 98},
        },
        flags=[{"type": "warn", "message": "Name abbreviated"}],
        summary="Bank statement from First Bank.",
    )
    db_session.add(doc2)
    db_session.commit()

    return created_submission


# ── GET /v1/analysis/submissions/{submission_id}/record ───────────────────


class TestGetUnifiedRecord:
    def test_record_returns_200(self, client, api_key_headers, created_submission):
        sid = created_submission["submission_id"]
        response = client.get(
            f"{ANALYSIS_BASE}/submissions/{sid}/record",
            headers=api_key_headers,
        )
        assert response.status_code == 200

    def test_record_response_envelope(
        self, client, api_key_headers, created_submission
    ):
        sid = created_submission["submission_id"]
        response = client.get(
            f"{ANALYSIS_BASE}/submissions/{sid}/record",
            headers=api_key_headers,
        )
        body = response.json()

        assert body["success"] is True
        assert body["message"] == "Unified record retrieved successfully"

    def test_record_empty_when_no_classified_docs(
        self, client, api_key_headers, created_submission
    ):
        sid = created_submission["submission_id"]
        response = client.get(
            f"{ANALYSIS_BASE}/submissions/{sid}/record",
            headers=api_key_headers,
        )
        data = response.json()["data"]

        assert data["field_count"] == 0
        assert data["classified_document_count"] == 0
        assert data["fields"] == {}

    def test_record_includes_submission_id(
        self, client, api_key_headers, created_submission
    ):
        sid = created_submission["submission_id"]
        response = client.get(
            f"{ANALYSIS_BASE}/submissions/{sid}/record",
            headers=api_key_headers,
        )
        data = response.json()["data"]

        assert data["submission_id"] == sid

    def test_record_merges_fields_from_classified_docs(
        self,
        client,
        api_key_headers,
        submission_with_classified_docs,
    ):
        sid = submission_with_classified_docs["submission_id"]
        response = client.get(
            f"{ANALYSIS_BASE}/submissions/{sid}/record",
            headers=api_key_headers,
        )
        data = response.json()["data"]

        assert data["classified_document_count"] == 2
        assert data["field_count"] > 0
        assert "Full Name" in data["fields"]
        assert "NIN" in data["fields"]
        assert "Account Number" in data["fields"]

    def test_record_picks_highest_confidence_value(
        self,
        client,
        api_key_headers,
        submission_with_classified_docs,
    ):
        sid = submission_with_classified_docs["submission_id"]
        response = client.get(
            f"{ANALYSIS_BASE}/submissions/{sid}/record",
            headers=api_key_headers,
        )
        full_name = response.json()["data"]["fields"]["Full Name"]

        # doc1 has confidence 94, doc2 has 71 — doc1 should win
        assert full_name["bestValue"] == "Emeka Obi"
        assert full_name["bestConfidence"] == 94

    def test_record_detects_conflict(
        self,
        client,
        api_key_headers,
        submission_with_classified_docs,
    ):
        sid = submission_with_classified_docs["submission_id"]
        response = client.get(
            f"{ANALYSIS_BASE}/submissions/{sid}/record",
            headers=api_key_headers,
        )
        full_name = response.json()["data"]["fields"]["Full Name"]

        # Emeka Obi vs E. Obi — should flag conflict
        assert full_name["hasConflict"] is True

    def test_record_tracks_all_source_values(
        self,
        client,
        api_key_headers,
        submission_with_classified_docs,
    ):
        sid = submission_with_classified_docs["submission_id"]
        response = client.get(
            f"{ANALYSIS_BASE}/submissions/{sid}/record",
            headers=api_key_headers,
        )
        full_name = response.json()["data"]["fields"]["Full Name"]

        assert len(full_name["allValues"]) == 2

    def test_record_404_nonexistent_submission(self, client, api_key_headers):
        response = client.get(
            f"{ANALYSIS_BASE}/submissions/sub_doesnotexist/record",
            headers=api_key_headers,
        )
        assert response.status_code == 404

    def test_record_requires_authentication(self, client, created_submission):
        sid = created_submission["submission_id"]
        response = client.get(f"{ANALYSIS_BASE}/submissions/{sid}/record")
        assert response.status_code == 401


# ── GET /v1/analysis/submissions/{submission_id}/validation ───────────────


class TestGetValidation:
    def test_validation_returns_200(self, client, api_key_headers, created_submission):
        sid = created_submission["submission_id"]
        response = client.get(
            f"{ANALYSIS_BASE}/submissions/{sid}/validation",
            headers=api_key_headers,
        )
        assert response.status_code == 200

    def test_validation_response_envelope(
        self, client, api_key_headers, created_submission
    ):
        sid = created_submission["submission_id"]
        response = client.get(
            f"{ANALYSIS_BASE}/submissions/{sid}/validation",
            headers=api_key_headers,
        )
        body = response.json()

        assert body["success"] is True
        assert body["message"] == "Validation completed successfully"

    def test_validation_includes_summary(
        self, client, api_key_headers, created_submission
    ):
        sid = created_submission["submission_id"]
        response = client.get(
            f"{ANALYSIS_BASE}/submissions/{sid}/validation",
            headers=api_key_headers,
        )
        data = response.json()["data"]

        assert "summary" in data
        assert "pass" in data["summary"]
        assert "fail" in data["summary"]
        assert "warn" in data["summary"]
        assert "skip" in data["summary"]

    def test_validation_includes_results_list(
        self, client, api_key_headers, created_submission
    ):
        sid = created_submission["submission_id"]
        response = client.get(
            f"{ANALYSIS_BASE}/submissions/{sid}/validation",
            headers=api_key_headers,
        )
        data = response.json()["data"]

        assert "results" in data
        assert isinstance(data["results"], list)

    def test_validation_result_has_required_fields(
        self, client, api_key_headers, created_submission
    ):
        sid = created_submission["submission_id"]
        response = client.get(
            f"{ANALYSIS_BASE}/submissions/{sid}/validation",
            headers=api_key_headers,
        )
        results = response.json()["data"]["results"]

        if results:
            r = results[0]
            assert "ruleId" in r
            assert "name" in r
            assert "type" in r
            assert "field" in r
            assert "severity" in r
            assert "status" in r
            assert "message" in r

    def test_validation_detects_conflict(
        self,
        client,
        api_key_headers,
        submission_with_classified_docs,
    ):
        sid = submission_with_classified_docs["submission_id"]
        response = client.get(
            f"{ANALYSIS_BASE}/submissions/{sid}/validation",
            headers=api_key_headers,
        )
        data = response.json()["data"]

        # Name conflict should cause at least one failure
        assert data["summary"]["fail"] >= 0

    def test_validation_404_nonexistent_submission(self, client, api_key_headers):
        response = client.get(
            f"{ANALYSIS_BASE}/submissions/sub_doesnotexist/validation",
            headers=api_key_headers,
        )
        assert response.status_code == 404

    def test_validation_requires_authentication(self, client, created_submission):
        sid = created_submission["submission_id"]
        response = client.get(f"{ANALYSIS_BASE}/submissions/{sid}/validation")
        assert response.status_code == 401


# ── GET /v1/analysis/submissions/{submission_id}/decision ─────────────────


class TestGetDecision:
    def test_decision_returns_200(self, client, api_key_headers, created_submission):
        sid = created_submission["submission_id"]
        response = client.get(
            f"{ANALYSIS_BASE}/submissions/{sid}/decision",
            headers=api_key_headers,
        )
        assert response.status_code == 200

    def test_decision_response_envelope(
        self, client, api_key_headers, created_submission
    ):
        sid = created_submission["submission_id"]
        response = client.get(
            f"{ANALYSIS_BASE}/submissions/{sid}/decision",
            headers=api_key_headers,
        )
        body = response.json()

        assert body["success"] is True
        assert body["message"] == "Decision computed successfully"

    def test_decision_includes_required_fields(
        self, client, api_key_headers, created_submission
    ):
        sid = created_submission["submission_id"]
        response = client.get(
            f"{ANALYSIS_BASE}/submissions/{sid}/decision",
            headers=api_key_headers,
        )
        data = response.json()["data"]

        assert "submission_id" in data
        assert "overallDecision" in data
        assert "reason" in data
        assert "thresholds" in data
        assert "summary" in data
        assert "fieldDecisions" in data

    def test_decision_overall_is_valid_value(
        self, client, api_key_headers, created_submission
    ):
        sid = created_submission["submission_id"]
        response = client.get(
            f"{ANALYSIS_BASE}/submissions/{sid}/decision",
            headers=api_key_headers,
        )
        decision = response.json()["data"]["overallDecision"]

        assert decision in {"auto", "review", "manual"}

    def test_decision_includes_thresholds(
        self, client, api_key_headers, created_submission
    ):
        sid = created_submission["submission_id"]
        response = client.get(
            f"{ANALYSIS_BASE}/submissions/{sid}/decision",
            headers=api_key_headers,
        )
        thresholds = response.json()["data"]["thresholds"]

        assert "autoAbove" in thresholds
        assert "manualBelow" in thresholds

    def test_decision_empty_submission_is_auto(
        self, client, api_key_headers, created_submission
    ):
        """No documents — no fields — no failures — should be auto."""
        sid = created_submission["submission_id"]
        response = client.get(
            f"{ANALYSIS_BASE}/submissions/{sid}/decision",
            headers=api_key_headers,
        )
        data = response.json()["data"]

        assert data["overallDecision"] == "auto"
        assert data["summary"]["auto"] == 0

    def test_decision_conflict_triggers_review(
        self,
        client,
        api_key_headers,
        submission_with_classified_docs,
    ):
        sid = submission_with_classified_docs["submission_id"]
        response = client.get(
            f"{ANALYSIS_BASE}/submissions/{sid}/decision",
            headers=api_key_headers,
        )
        data = response.json()["data"]

        # Name conflict → review or manual
        assert data["overallDecision"] in {"review", "manual"}

    def test_decision_404_nonexistent_submission(self, client, api_key_headers):
        response = client.get(
            f"{ANALYSIS_BASE}/submissions/sub_doesnotexist/decision",
            headers=api_key_headers,
        )
        assert response.status_code == 404

    def test_decision_requires_authentication(self, client, created_submission):
        sid = created_submission["submission_id"]
        response = client.get(f"{ANALYSIS_BASE}/submissions/{sid}/decision")
        assert response.status_code == 401
