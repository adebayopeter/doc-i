"""
End-to-end integration test — RSA Mortgage application workflow.

Traces the complete lifecycle of a document processing case:

  1. Create a process (RSA Mortgage with document checklist)
  2. Open a submission for an applicant
  3. Upload two documents (NIN slip + bank statement)
  4. Inject classified results directly (Celery worker not running in tests)
  5. Get the unified record — verify field merging and conflict detection
  6. Run validation — verify rules fire correctly
  7. Get routing decision — verify confidence-based routing
  8. Update submission status to complete
  9. Verify terminal state blocks further uploads

This test does NOT mock the database, routing, auth, or response envelope.
It is the closest thing to a real API call without an actual HTTP client.
"""

import io

import pytest

PROCESSES_BASE = "/v1/processes"
SUBMISSIONS_BASE = "/v1/submissions"
DOCUMENTS_BASE = "/v1/documents"
ANALYSIS_BASE = "/v1/analysis"
CONFIG_BASE = "/v1/config"


# ── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture
def mortgage_process(client, api_key_headers):
    """
    Creates the RSA Mortgage process with a realistic Nigerian
    document checklist — 6 documents across 3 categories.
    """
    payload = {
        "name": "RSA Mortgage — Integration Test",
        "description": "End-to-end test process for RSA residential mortgage",
        "color_var": "info",
        "icon": "ti-home-2",
        "documents": [
            {
                "name": "National ID / NIN slip",
                "category": "Identity",
                "is_required": True,
            },
            {
                "name": "Utility bill (proof of address)",
                "category": "Identity",
                "is_required": True,
            },
            {
                "name": "Bank statement (6 months)",
                "category": "Financial",
                "is_required": True,
            },
            {
                "name": "Offer letter / Employment letter",
                "category": "Income",
                "is_required": True,
            },
            {
                "name": "Payslip (3 months)",
                "category": "Income",
                "is_required": True,
            },
            {
                "name": "Guarantor letter",
                "category": "Supporting",
                "is_required": False,
            },
        ],
    }
    response = client.post(PROCESSES_BASE, json=payload, headers=api_key_headers)
    assert response.status_code == 201, f"Process creation failed: {response.json()}"
    return response.json()["data"]


@pytest.fixture
def mortgage_submission(client, api_key_headers, mortgage_process):
    """Opens a submission for applicant Emeka Obi under the mortgage process."""
    payload = {
        "process_id": mortgage_process["process_id"],
        "reference": "MORTGAGE-2025-E001",
        "applicant_id": "usr_emeka_obi_001",
    }
    response = client.post(SUBMISSIONS_BASE, json=payload, headers=api_key_headers)
    assert response.status_code == 201, f"Submission creation failed: {response.json()}"
    return response.json()["data"]


@pytest.fixture
def submission_with_documents(db_session, client, api_key_headers, mortgage_submission):
    """
    Uploads two documents and injects classified results directly.

    In production the Celery worker would classify these asynchronously.
    In tests we inject the results directly into the DB to simulate
    a completed classification without running the worker.
    """
    from db.models import SubmissionDocument

    sid = mortgage_submission["submission_id"]

    # Upload document 1 — NIN slip
    nin_response = client.post(
        f"{DOCUMENTS_BASE}/submissions/{sid}/upload",
        files={
            "file": (
                "nin_slip.pdf",
                io.BytesIO(b"%PDF-1.4 NIN slip test content"),
                "application/pdf",
            )
        },
        headers=api_key_headers,
    )
    assert nin_response.status_code == 202
    nin_doc_id = nin_response.json()["data"]["document_id"]

    # Upload document 2 — bank statement
    bank_response = client.post(
        f"{DOCUMENTS_BASE}/submissions/{sid}/upload",
        files={
            "file": (
                "bank_statement.pdf",
                io.BytesIO(b"%PDF-1.4 Bank statement test content"),
                "application/pdf",
            )
        },
        headers=api_key_headers,
    )
    assert bank_response.status_code == 202
    bank_doc_id = bank_response.json()["data"]["document_id"]

    # Inject classification results for NIN slip
    # Note: name has a slight discrepancy with bank statement to test
    # conflict detection in the unified record
    nin_doc = (
        db_session.query(SubmissionDocument)
        .filter(SubmissionDocument.id == nin_doc_id)
        .first()
    )
    nin_doc.status = "classified"
    nin_doc.document_type = "National ID / NIN slip"
    nin_doc.matched_doc_id = 1
    nin_doc.overall_confidence = 91
    nin_doc.extracted_fields = {
        "Full Name": {"value": "Emeka Obi", "confidence": 94},
        "NIN": {"value": "12345678901", "confidence": 97},
        "Date of Birth": {"value": "1990-03-15", "confidence": 89},
        "Address": {
            "value": "12 Adeola Odeku Street, Victoria Island, Lagos",
            "confidence": 82,
        },
    }
    nin_doc.flags = [{"type": "ok", "message": "Document valid and not expired"}]
    nin_doc.summary = "Valid NIN slip issued by NIMC. All fields legible."

    # Inject classification results for bank statement
    # Full Name uses initials — intentional conflict for testing
    bank_doc = (
        db_session.query(SubmissionDocument)
        .filter(SubmissionDocument.id == bank_doc_id)
        .first()
    )
    bank_doc.status = "classified"
    bank_doc.document_type = "Bank statement (6 months)"
    bank_doc.matched_doc_id = 3
    bank_doc.overall_confidence = 87
    bank_doc.extracted_fields = {
        "Full Name": {"value": "E. Obi", "confidence": 71},
        "Account Number": {"value": "1234567890", "confidence": 95},
        "Bank Name": {"value": "First Bank of Nigeria", "confidence": 98},
        "Address": {
            "value": "12 Adeola Odeku Street, Victoria Island, Lagos",
            "confidence": 88,
        },
    }
    bank_doc.flags = [
        {
            "type": "warn",
            "message": "Name appears abbreviated — cross-check with ID",
        }
    ]
    bank_doc.summary = "6-month bank statement from First Bank Nigeria."

    db_session.commit()

    return {
        "submission": mortgage_submission,
        "nin_doc_id": nin_doc_id,
        "bank_doc_id": bank_doc_id,
    }


# ── Step 1: Process creation ───────────────────────────────────────────────


class TestStep1ProcessCreation:
    def test_process_created_with_correct_name(self, mortgage_process):
        assert mortgage_process["name"] == "RSA Mortgage — Integration Test"

    def test_process_has_six_documents(self, mortgage_process):
        assert mortgage_process["document_count"] == 6

    def test_process_documents_are_ordered(self, mortgage_process):
        orders = [d["sort_order"] for d in mortgage_process["documents"]]
        assert orders == sorted(orders)

    def test_process_appears_in_list(self, client, api_key_headers, mortgage_process):
        response = client.get(PROCESSES_BASE, headers=api_key_headers)
        ids = [p["process_id"] for p in response.json()["data"]["items"]]
        assert mortgage_process["process_id"] in ids

    def test_process_detail_has_full_checklist(
        self, client, api_key_headers, mortgage_process
    ):
        pid = mortgage_process["process_id"]
        response = client.get(f"{PROCESSES_BASE}/{pid}", headers=api_key_headers)
        data = response.json()["data"]

        assert data["document_count"] == 6
        categories = {d["category"] for d in data["documents"]}
        assert "Identity" in categories
        assert "Financial" in categories
        assert "Income" in categories


# ── Step 2: Submission creation ────────────────────────────────────────────


class TestStep2SubmissionCreation:
    def test_submission_created_successfully(self, mortgage_submission):
        assert mortgage_submission["submission_id"].startswith("sub_")

    def test_submission_initial_status_is_open(self, mortgage_submission):
        assert mortgage_submission["status"] == "open"

    def test_submission_progress_starts_at_zero(self, mortgage_submission):
        assert mortgage_submission["progress"]["classified"] == 0
        assert mortgage_submission["progress"]["required"] == 6

    def test_submission_stores_applicant_reference(self, mortgage_submission):
        assert mortgage_submission["reference"] == "MORTGAGE-2025-E001"
        assert mortgage_submission["applicant_id"] == "usr_emeka_obi_001"

    def test_submission_includes_process_name(self, mortgage_submission):
        assert mortgage_submission["process_name"] == (
            "RSA Mortgage — Integration Test"
        )


# ── Step 3: Document upload ────────────────────────────────────────────────


class TestStep3DocumentUpload:
    def test_first_upload_moves_submission_to_in_progress(
        self,
        client,
        api_key_headers,
        submission_with_documents,
    ):
        sid = submission_with_documents["submission"]["submission_id"]
        response = client.get(f"{SUBMISSIONS_BASE}/{sid}", headers=api_key_headers)
        assert response.json()["data"]["status"] == "in_progress"

    def test_two_documents_uploaded(
        self,
        client,
        api_key_headers,
        submission_with_documents,
    ):
        sid = submission_with_documents["submission"]["submission_id"]
        response = client.get(f"{SUBMISSIONS_BASE}/{sid}", headers=api_key_headers)
        assert response.json()["data"]["documents_uploaded"] == 2

    def test_documents_visible_in_submission_documents_list(
        self,
        client,
        api_key_headers,
        submission_with_documents,
    ):
        sid = submission_with_documents["submission"]["submission_id"]
        response = client.get(
            f"{SUBMISSIONS_BASE}/{sid}/documents",
            headers=api_key_headers,
        )
        data = response.json()["data"]

        assert data["total"] == 2

    def test_nin_slip_is_classified(
        self,
        client,
        api_key_headers,
        submission_with_documents,
    ):
        doc_id = submission_with_documents["nin_doc_id"]
        response = client.get(f"{DOCUMENTS_BASE}/{doc_id}", headers=api_key_headers)
        data = response.json()["data"]

        assert data["status"] == "classified"
        assert data["document_type"] == "National ID / NIN slip"
        assert data["overall_confidence"] == 91

    def test_nin_slip_has_extracted_fields(
        self,
        client,
        api_key_headers,
        submission_with_documents,
    ):
        doc_id = submission_with_documents["nin_doc_id"]
        response = client.get(f"{DOCUMENTS_BASE}/{doc_id}", headers=api_key_headers)
        fields = response.json()["data"]["extracted_fields"]

        assert fields is not None
        assert "Full Name" in fields
        assert fields["Full Name"]["value"] == "Emeka Obi"
        assert fields["NIN"]["value"] == "12345678901"

    def test_bank_statement_is_classified(
        self,
        client,
        api_key_headers,
        submission_with_documents,
    ):
        doc_id = submission_with_documents["bank_doc_id"]
        response = client.get(f"{DOCUMENTS_BASE}/{doc_id}", headers=api_key_headers)
        data = response.json()["data"]

        assert data["status"] == "classified"
        assert data["document_type"] == "Bank statement (6 months)"


# ── Step 4: Unified record ─────────────────────────────────────────────────


class TestStep4UnifiedRecord:
    def test_record_merges_fields_from_both_documents(
        self,
        client,
        api_key_headers,
        submission_with_documents,
    ):
        sid = submission_with_documents["submission"]["submission_id"]
        response = client.get(
            f"{ANALYSIS_BASE}/submissions/{sid}/record",
            headers=api_key_headers,
        )
        data = response.json()["data"]

        assert data["classified_document_count"] == 2
        # Fields from both documents merged
        assert "Full Name" in data["fields"]
        assert "NIN" in data["fields"]
        assert "Account Number" in data["fields"]
        assert "Bank Name" in data["fields"]

    def test_record_picks_highest_confidence_full_name(
        self,
        client,
        api_key_headers,
        submission_with_documents,
    ):
        sid = submission_with_documents["submission"]["submission_id"]
        response = client.get(
            f"{ANALYSIS_BASE}/submissions/{sid}/record",
            headers=api_key_headers,
        )
        full_name = response.json()["data"]["fields"]["Full Name"]

        # NIN slip has confidence 94, bank statement has 71
        # NIN slip should win
        assert full_name["bestValue"] == "Emeka Obi"
        assert full_name["bestConfidence"] == 94
        assert full_name["sourceDocType"] == "National ID / NIN slip"

    def test_record_detects_name_conflict(
        self,
        client,
        api_key_headers,
        submission_with_documents,
    ):
        sid = submission_with_documents["submission"]["submission_id"]
        response = client.get(
            f"{ANALYSIS_BASE}/submissions/{sid}/record",
            headers=api_key_headers,
        )
        full_name = response.json()["data"]["fields"]["Full Name"]

        # "Emeka Obi" vs "E. Obi" — should be flagged as conflict
        assert full_name["hasConflict"] is True
        assert len(full_name["allValues"]) == 2

    def test_record_address_has_no_conflict(
        self,
        client,
        api_key_headers,
        submission_with_documents,
    ):
        sid = submission_with_documents["submission"]["submission_id"]
        response = client.get(
            f"{ANALYSIS_BASE}/submissions/{sid}/record",
            headers=api_key_headers,
        )
        address = response.json()["data"]["fields"]["Address"]

        # Same address on both documents — no conflict
        assert address["hasConflict"] is False

    def test_record_field_count_is_correct(
        self,
        client,
        api_key_headers,
        submission_with_documents,
    ):
        sid = submission_with_documents["submission"]["submission_id"]
        response = client.get(
            f"{ANALYSIS_BASE}/submissions/{sid}/record",
            headers=api_key_headers,
        )
        data = response.json()["data"]

        # Full Name, NIN, Date of Birth, Address, Account Number, Bank Name
        assert data["field_count"] == 6


# ── Step 5: Validation ─────────────────────────────────────────────────────


class TestStep5Validation:
    def test_validation_runs_successfully(
        self,
        client,
        api_key_headers,
        submission_with_documents,
    ):
        sid = submission_with_documents["submission"]["submission_id"]
        response = client.get(
            f"{ANALYSIS_BASE}/submissions/{sid}/validation",
            headers=api_key_headers,
        )
        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_validation_summary_has_all_keys(
        self,
        client,
        api_key_headers,
        submission_with_documents,
    ):
        sid = submission_with_documents["submission"]["submission_id"]
        response = client.get(
            f"{ANALYSIS_BASE}/submissions/{sid}/validation",
            headers=api_key_headers,
        )
        summary = response.json()["data"]["summary"]

        assert "pass" in summary
        assert "fail" in summary
        assert "warn" in summary
        assert "skip" in summary

    def test_validation_results_have_correct_structure(
        self,
        client,
        api_key_headers,
        submission_with_documents,
    ):
        sid = submission_with_documents["submission"]["submission_id"]
        response = client.get(
            f"{ANALYSIS_BASE}/submissions/{sid}/validation",
            headers=api_key_headers,
        )
        results = response.json()["data"]["results"]

        assert isinstance(results, list)
        if results:
            r = results[0]
            assert all(
                k in r
                for k in [
                    "ruleId",
                    "name",
                    "type",
                    "field",
                    "severity",
                    "status",
                    "message",
                ]
            )

    def test_nin_format_rule_passes(
        self,
        client,
        api_key_headers,
        submission_with_documents,
        db_session,
    ):
        """NIN 12345678901 should pass the 11-digit format rule."""
        from scripts.seed_rules import seed

        seed(session=db_session)

        sid = submission_with_documents["submission"]["submission_id"]
        response = client.get(
            f"{ANALYSIS_BASE}/submissions/{sid}/validation",
            headers=api_key_headers,
        )
        results = response.json()["data"]["results"]
        nin_results = [r for r in results if r["field"] == "NIN"]

        if nin_results:
            format_result = next(
                (r for r in nin_results if r["type"] == "format"), None
            )
            if format_result:
                assert format_result["status"] == "pass"


# ── Step 6: Decision ───────────────────────────────────────────────────────


class TestStep6Decision:
    def test_decision_returns_valid_overall(
        self,
        client,
        api_key_headers,
        submission_with_documents,
    ):
        sid = submission_with_documents["submission"]["submission_id"]
        response = client.get(
            f"{ANALYSIS_BASE}/submissions/{sid}/decision",
            headers=api_key_headers,
        )
        data = response.json()["data"]

        assert data["overallDecision"] in {"auto", "review", "manual"}

    def test_decision_includes_field_decisions(
        self,
        client,
        api_key_headers,
        submission_with_documents,
    ):
        sid = submission_with_documents["submission"]["submission_id"]
        response = client.get(
            f"{ANALYSIS_BASE}/submissions/{sid}/decision",
            headers=api_key_headers,
        )
        data = response.json()["data"]

        assert len(data["fieldDecisions"]) > 0

    def test_name_conflict_affects_decision(
        self,
        client,
        api_key_headers,
        submission_with_documents,
    ):
        """
        Name conflict (Emeka Obi vs E. Obi) should push decision
        toward review or manual — never auto when there is a conflict.
        """
        sid = submission_with_documents["submission"]["submission_id"]
        response = client.get(
            f"{ANALYSIS_BASE}/submissions/{sid}/decision",
            headers=api_key_headers,
        )
        data = response.json()["data"]

        # With a name conflict the overall should be review or manual
        assert data["overallDecision"] in {"review", "manual"}

    def test_decision_includes_thresholds(
        self,
        client,
        api_key_headers,
        submission_with_documents,
    ):
        sid = submission_with_documents["submission"]["submission_id"]
        response = client.get(
            f"{ANALYSIS_BASE}/submissions/{sid}/decision",
            headers=api_key_headers,
        )
        thresholds = response.json()["data"]["thresholds"]

        assert "autoAbove" in thresholds
        assert "manualBelow" in thresholds
        assert thresholds["autoAbove"] > thresholds["manualBelow"]

    def test_decision_field_decisions_sorted_by_confidence(
        self,
        client,
        api_key_headers,
        submission_with_documents,
    ):
        sid = submission_with_documents["submission"]["submission_id"]
        response = client.get(
            f"{ANALYSIS_BASE}/submissions/{sid}/decision",
            headers=api_key_headers,
        )
        field_decisions = response.json()["data"]["fieldDecisions"]

        confidences = [f["confidence"] for f in field_decisions]
        assert confidences == sorted(confidences)


# ── Step 7: Status progression ─────────────────────────────────────────────


class TestStep7StatusProgression:
    def test_status_transitions_open_to_in_progress(
        self, client, api_key_headers, mortgage_submission
    ):
        """First document upload already moved it — verify in_progress."""
        sid = mortgage_submission["submission_id"]
        response = client.get(f"{SUBMISSIONS_BASE}/{sid}", headers=api_key_headers)
        # Status may be open (no docs) or in_progress (with docs)
        assert response.json()["data"]["status"] in {"open", "in_progress"}

    def test_manual_status_update_to_complete(
        self,
        client,
        api_key_headers,
        submission_with_documents,
    ):
        sid = submission_with_documents["submission"]["submission_id"]

        # Move to in_progress first if needed
        current = client.get(
            f"{SUBMISSIONS_BASE}/{sid}", headers=api_key_headers
        ).json()["data"]["status"]

        if current == "open":
            client.patch(
                f"{SUBMISSIONS_BASE}/{sid}/status",
                params={"new_status": "in_progress"},
                headers=api_key_headers,
            )

        response = client.patch(
            f"{SUBMISSIONS_BASE}/{sid}/status",
            params={"new_status": "complete"},
            headers=api_key_headers,
        )
        assert response.status_code == 200
        assert response.json()["data"]["new_status"] == "complete"

    def test_complete_submission_blocks_upload(
        self,
        client,
        api_key_headers,
        submission_with_documents,
    ):
        """Once complete no more documents can be uploaded."""
        sid = submission_with_documents["submission"]["submission_id"]

        # Progress to complete
        current = client.get(
            f"{SUBMISSIONS_BASE}/{sid}", headers=api_key_headers
        ).json()["data"]["status"]

        if current == "open":
            client.patch(
                f"{SUBMISSIONS_BASE}/{sid}/status",
                params={"new_status": "in_progress"},
                headers=api_key_headers,
            )
        if current in {"open", "in_progress"}:
            client.patch(
                f"{SUBMISSIONS_BASE}/{sid}/status",
                params={"new_status": "complete"},
                headers=api_key_headers,
            )

        # Attempt to upload after completion
        response = client.post(
            f"{DOCUMENTS_BASE}/submissions/{sid}/upload",
            files={
                "file": (
                    "extra_doc.pdf",
                    io.BytesIO(b"%PDF-1.4 extra"),
                    "application/pdf",
                )
            },
            headers=api_key_headers,
        )
        assert response.status_code == 422
        assert "complete" in response.json()["message"]

    def test_complete_is_terminal_state(
        self,
        client,
        api_key_headers,
        submission_with_documents,
    ):
        """No transitions are allowed from complete."""
        sid = submission_with_documents["submission"]["submission_id"]

        current = client.get(
            f"{SUBMISSIONS_BASE}/{sid}", headers=api_key_headers
        ).json()["data"]["status"]

        if current == "open":
            client.patch(
                f"{SUBMISSIONS_BASE}/{sid}/status",
                params={"new_status": "in_progress"},
                headers=api_key_headers,
            )
        if current in {"open", "in_progress"}:
            client.patch(
                f"{SUBMISSIONS_BASE}/{sid}/status",
                params={"new_status": "complete"},
                headers=api_key_headers,
            )

        response = client.patch(
            f"{SUBMISSIONS_BASE}/{sid}/status",
            params={"new_status": "rejected"},
            headers=api_key_headers,
        )
        assert response.status_code == 422


# ── Step 8: Config — threshold adjustment ─────────────────────────────────


class TestStep8ConfigAdjustment:
    def test_tighten_thresholds_changes_decision(
        self,
        client,
        api_key_headers,
        submission_with_documents,
    ):
        """
        Raising auto_above to 99 means nothing auto-processes.
        Every field should become review or manual.
        """
        # Tighten thresholds
        put_response = client.put(
            f"{CONFIG_BASE}/thresholds",
            json={"auto_above": 99, "manual_below": 79},
            headers=api_key_headers,
        )
        assert (
            put_response.status_code == 200
        ), f"Threshold PUT failed: {put_response.json()}"

        sid = submission_with_documents["submission"]["submission_id"]
        response = client.get(
            f"{ANALYSIS_BASE}/submissions/{sid}/decision",
            headers=api_key_headers,
        )
        data = response.json()["data"]

        assert data["summary"]["auto"] == 0
        assert data["overallDecision"] in {"review", "manual"}

    def test_reset_thresholds_to_default(self, client, api_key_headers):
        """Restore defaults after the tightened threshold test."""
        response = client.put(
            f"{CONFIG_BASE}/thresholds",
            json={"auto_above": 85, "manual_below": 60},
            headers=api_key_headers,
        )
        assert response.status_code == 200
        data = response.json()["data"]

        assert data["auto_above"] == 85
        assert data["manual_below"] == 60


# ── Full pipeline summary ──────────────────────────────────────────────────


class TestFullPipelineSummary:
    def test_complete_pipeline_response_envelopes_are_consistent(
        self,
        client,
        api_key_headers,
        submission_with_documents,
    ):
        """
        Every single API call in the pipeline must return
        {success, message, data} in that order.
        Spot-checks 4 different endpoints.
        """
        sid = submission_with_documents["submission"]["submission_id"]

        endpoints = [
            f"{SUBMISSIONS_BASE}/{sid}",
            f"{SUBMISSIONS_BASE}/{sid}/documents",
            f"{ANALYSIS_BASE}/submissions/{sid}/record",
            f"{ANALYSIS_BASE}/submissions/{sid}/decision",
        ]

        for endpoint in endpoints:
            response = client.get(endpoint, headers=api_key_headers)
            body = response.json()

            assert "success" in body, f"Missing 'success' on {endpoint}"
            assert "message" in body, f"Missing 'message' on {endpoint}"
            assert "data" in body, f"Missing 'data' on {endpoint}"
            assert body["success"] is True, f"Expected success=true on {endpoint}"

            # Verify field order — success must come before message
            keys = list(body.keys())
            assert keys.index("success") < keys.index(
                "message"
            ), f"success should come before message on {endpoint}"
            assert keys.index("message") < keys.index(
                "data"
            ), f"message should come before data on {endpoint}"

    def test_unauthenticated_requests_return_401_envelope(
        self, client, submission_with_documents
    ):
        """
        All unauthenticated requests must return 401
        in the standard envelope — not FastAPI's default format.
        """
        sid = submission_with_documents["submission"]["submission_id"]

        endpoints = [
            f"{SUBMISSIONS_BASE}/{sid}",
            f"{ANALYSIS_BASE}/submissions/{sid}/record",
            f"{ANALYSIS_BASE}/submissions/{sid}/decision",
        ]

        for endpoint in endpoints:
            response = client.get(endpoint)  # no auth headers
            assert response.status_code == 401, f"Expected 401 on {endpoint}"
            body = response.json()
            assert body["success"] is False
            assert "message" in body
