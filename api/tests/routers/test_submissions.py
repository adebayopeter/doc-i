"""
Tests for /v1/submissions endpoints.
"""

import pytest

SUBMISSIONS_BASE = "/v1/submissions"
PROCESSES_BASE = "/v1/processes"


# ── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture
def process_payload():
    return {
        "name": "RSA Mortgage",
        "description": "Residential mortgage application",
        "documents": [
            {"name": "National ID / NIN slip", "category": "Identity"},
            {"name": "Bank statement (6 months)", "category": "Financial"},
            {"name": "Offer letter", "category": "Income"},
        ],
    }


@pytest.fixture
def created_process(client, api_key_headers, process_payload):
    response = client.post(
        PROCESSES_BASE, json=process_payload, headers=api_key_headers
    )
    assert response.status_code == 201
    return response.json()["data"]


@pytest.fixture
def submission_payload(created_process):
    return {
        "process_id": created_process["process_id"],
        "reference": "APP-2025-001",
        "applicant_id": "usr_emeka_obi",
    }


@pytest.fixture
def created_submission(client, api_key_headers, submission_payload):
    response = client.post(
        SUBMISSIONS_BASE, json=submission_payload, headers=api_key_headers
    )
    assert response.status_code == 201
    return response.json()["data"]


# ── POST /v1/submissions ───────────────────────────────────────────────────


class TestCreateSubmission:
    def test_create_returns_201(self, client, api_key_headers, submission_payload):
        response = client.post(
            SUBMISSIONS_BASE, json=submission_payload, headers=api_key_headers
        )
        assert response.status_code == 201

    def test_create_response_envelope(
        self, client, api_key_headers, submission_payload
    ):
        response = client.post(
            SUBMISSIONS_BASE, json=submission_payload, headers=api_key_headers
        )
        body = response.json()

        assert body["success"] is True
        assert body["message"] == "Submission opened successfully"
        assert body["data"] is not None

    def test_create_returns_submission_id(
        self, client, api_key_headers, submission_payload
    ):
        response = client.post(
            SUBMISSIONS_BASE, json=submission_payload, headers=api_key_headers
        )
        data = response.json()["data"]

        assert "submission_id" in data
        assert data["submission_id"].startswith("sub_")

    def test_create_stores_all_fields(
        self, client, api_key_headers, submission_payload
    ):
        response = client.post(
            SUBMISSIONS_BASE, json=submission_payload, headers=api_key_headers
        )
        data = response.json()["data"]

        assert data["reference"] == "APP-2025-001"
        assert data["applicant_id"] == "usr_emeka_obi"

    def test_create_initial_status_is_open(
        self, client, api_key_headers, submission_payload
    ):
        response = client.post(
            SUBMISSIONS_BASE, json=submission_payload, headers=api_key_headers
        )
        data = response.json()["data"]

        assert data["status"] == "open"

    def test_create_initial_progress_is_zero(
        self, client, api_key_headers, submission_payload
    ):
        response = client.post(
            SUBMISSIONS_BASE, json=submission_payload, headers=api_key_headers
        )
        data = response.json()["data"]

        assert data["progress"]["classified"] == 0
        assert data["progress"]["required"] == 3
        assert data["documents_uploaded"] == 0

    def test_create_includes_process_name(
        self, client, api_key_headers, submission_payload
    ):
        response = client.post(
            SUBMISSIONS_BASE, json=submission_payload, headers=api_key_headers
        )
        data = response.json()["data"]

        assert data["process_name"] == "RSA Mortgage"

    def test_create_without_optional_fields(
        self, client, api_key_headers, created_process
    ):
        response = client.post(
            SUBMISSIONS_BASE,
            json={"process_id": created_process["process_id"]},
            headers=api_key_headers,
        )
        assert response.status_code == 201

        data = response.json()["data"]
        assert data["reference"] is None
        assert data["applicant_id"] is None

    def test_create_with_invalid_process_id(self, client, api_key_headers):
        response = client.post(
            SUBMISSIONS_BASE,
            json={"process_id": "proc_doesnotexist"},
            headers=api_key_headers,
        )
        assert response.status_code == 404

        body = response.json()
        assert body["success"] is False
        assert "Process not found" in body["message"]

    def test_create_requires_process_id(self, client, api_key_headers):
        response = client.post(
            SUBMISSIONS_BASE,
            json={"reference": "APP-2025-001"},
            headers=api_key_headers,
        )
        assert response.status_code == 422

    def test_create_requires_authentication(self, client, submission_payload):
        response = client.post(SUBMISSIONS_BASE, json=submission_payload)
        assert response.status_code == 401

    def test_multiple_submissions_same_process(
        self, client, api_key_headers, submission_payload
    ):
        """Same process can have multiple submissions."""
        r1 = client.post(
            SUBMISSIONS_BASE, json=submission_payload, headers=api_key_headers
        )
        r2 = client.post(
            SUBMISSIONS_BASE, json=submission_payload, headers=api_key_headers
        )
        assert r1.status_code == 201
        assert r2.status_code == 201
        assert r1.json()["data"]["submission_id"] != r2.json()["data"]["submission_id"]


# ── GET /v1/submissions ────────────────────────────────────────────────────


class TestListSubmissions:
    def test_list_returns_200(self, client, api_key_headers):
        response = client.get(SUBMISSIONS_BASE, headers=api_key_headers)
        assert response.status_code == 200

    def test_list_response_envelope(self, client, api_key_headers):
        response = client.get(SUBMISSIONS_BASE, headers=api_key_headers)
        body = response.json()

        assert body["success"] is True
        assert body["message"] == "Submissions retrieved successfully"
        assert body["data"] is not None

    def test_list_returns_items_and_total(self, client, api_key_headers):
        response = client.get(SUBMISSIONS_BASE, headers=api_key_headers)
        data = response.json()["data"]

        assert "items" in data
        assert "total" in data

    def test_list_includes_created_submission(
        self, client, api_key_headers, created_submission
    ):
        response = client.get(SUBMISSIONS_BASE, headers=api_key_headers)
        data = response.json()["data"]

        ids = [s["submission_id"] for s in data["items"]]
        assert created_submission["submission_id"] in ids

    def test_list_total_matches_items(
        self, client, api_key_headers, created_submission
    ):
        response = client.get(SUBMISSIONS_BASE, headers=api_key_headers)
        data = response.json()["data"]

        assert data["total"] == len(data["items"])

    def test_list_filter_by_process_id(
        self, client, api_key_headers, created_submission, created_process
    ):
        process_id = created_process["process_id"]
        response = client.get(
            f"{SUBMISSIONS_BASE}?process_id={process_id}",
            headers=api_key_headers,
        )
        data = response.json()["data"]

        for item in data["items"]:
            assert item["process_id"] == process_id

    def test_list_requires_authentication(self, client):
        response = client.get(SUBMISSIONS_BASE)
        assert response.status_code == 401


# ── GET /v1/submissions/{submission_id} ───────────────────────────────────


class TestGetSubmission:
    def test_get_returns_200(self, client, api_key_headers, created_submission):
        sid = created_submission["submission_id"]
        response = client.get(f"{SUBMISSIONS_BASE}/{sid}", headers=api_key_headers)
        assert response.status_code == 200

    def test_get_response_envelope(self, client, api_key_headers, created_submission):
        sid = created_submission["submission_id"]
        response = client.get(f"{SUBMISSIONS_BASE}/{sid}", headers=api_key_headers)
        body = response.json()

        assert body["success"] is True
        assert body["message"] == "Submission retrieved successfully"

    def test_get_returns_correct_data(
        self, client, api_key_headers, created_submission
    ):
        sid = created_submission["submission_id"]
        response = client.get(f"{SUBMISSIONS_BASE}/{sid}", headers=api_key_headers)
        data = response.json()["data"]

        assert data["submission_id"] == sid
        assert data["reference"] == "APP-2025-001"
        assert data["status"] == "open"

    def test_get_nonexistent_submission(self, client, api_key_headers):
        response = client.get(
            f"{SUBMISSIONS_BASE}/sub_doesnotexist",
            headers=api_key_headers,
        )
        assert response.status_code == 404

        body = response.json()
        assert body["success"] is False
        assert body["message"] == "Submission not found"

    def test_get_requires_authentication(self, client, created_submission):
        sid = created_submission["submission_id"]
        response = client.get(f"{SUBMISSIONS_BASE}/{sid}")
        assert response.status_code == 401


# ── GET /v1/submissions/{submission_id}/documents ─────────────────────────


class TestListSubmissionDocuments:
    def test_list_docs_returns_200(self, client, api_key_headers, created_submission):
        sid = created_submission["submission_id"]
        response = client.get(
            f"{SUBMISSIONS_BASE}/{sid}/documents",
            headers=api_key_headers,
        )
        assert response.status_code == 200

    def test_list_docs_response_envelope(
        self, client, api_key_headers, created_submission
    ):
        sid = created_submission["submission_id"]
        response = client.get(
            f"{SUBMISSIONS_BASE}/{sid}/documents",
            headers=api_key_headers,
        )
        body = response.json()

        assert body["success"] is True
        assert body["message"] == "Documents retrieved successfully"

    def test_list_docs_empty_for_new_submission(
        self, client, api_key_headers, created_submission
    ):
        sid = created_submission["submission_id"]
        response = client.get(
            f"{SUBMISSIONS_BASE}/{sid}/documents",
            headers=api_key_headers,
        )
        data = response.json()["data"]

        assert data["total"] == 0
        assert data["classified"] == 0
        assert data["processing"] == 0
        assert data["failed"] == 0
        assert data["documents"] == []

    def test_list_docs_includes_submission_id(
        self, client, api_key_headers, created_submission
    ):
        sid = created_submission["submission_id"]
        response = client.get(
            f"{SUBMISSIONS_BASE}/{sid}/documents",
            headers=api_key_headers,
        )
        data = response.json()["data"]

        assert data["submission_id"] == sid

    def test_list_docs_404_for_nonexistent_submission(self, client, api_key_headers):
        response = client.get(
            f"{SUBMISSIONS_BASE}/sub_doesnotexist/documents",
            headers=api_key_headers,
        )
        assert response.status_code == 404

    def test_list_docs_requires_authentication(self, client, created_submission):
        sid = created_submission["submission_id"]
        response = client.get(f"{SUBMISSIONS_BASE}/{sid}/documents")
        assert response.status_code == 401


# ── PATCH /v1/submissions/{submission_id}/status ──────────────────────────


class TestUpdateSubmissionStatus:
    def test_update_status_returns_200(
        self, client, api_key_headers, created_submission
    ):
        sid = created_submission["submission_id"]
        response = client.patch(
            f"{SUBMISSIONS_BASE}/{sid}/status",
            params={"new_status": "in_progress"},
            headers=api_key_headers,
        )
        assert response.status_code == 200

    def test_update_status_response_envelope(
        self, client, api_key_headers, created_submission
    ):
        sid = created_submission["submission_id"]
        response = client.patch(
            f"{SUBMISSIONS_BASE}/{sid}/status",
            params={"new_status": "in_progress"},
            headers=api_key_headers,
        )
        body = response.json()

        assert body["success"] is True
        assert "in_progress" in body["message"]

    def test_update_status_returns_transition_data(
        self, client, api_key_headers, created_submission
    ):
        sid = created_submission["submission_id"]
        response = client.patch(
            f"{SUBMISSIONS_BASE}/{sid}/status",
            params={"new_status": "in_progress"},
            headers=api_key_headers,
        )
        data = response.json()["data"]

        assert data["submission_id"] == sid
        assert data["previous_status"] == "open"
        assert data["new_status"] == "in_progress"

    def test_update_status_persists(self, client, api_key_headers, created_submission):
        sid = created_submission["submission_id"]
        client.patch(
            f"{SUBMISSIONS_BASE}/{sid}/status",
            params={"new_status": "in_progress"},
            headers=api_key_headers,
        )
        response = client.get(f"{SUBMISSIONS_BASE}/{sid}", headers=api_key_headers)
        assert response.json()["data"]["status"] == "in_progress"

    def test_update_status_valid_transition_to_complete(
        self, client, api_key_headers, created_submission
    ):
        sid = created_submission["submission_id"]
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

    def test_update_status_invalid_value(
        self, client, api_key_headers, created_submission
    ):
        sid = created_submission["submission_id"]
        response = client.patch(
            f"{SUBMISSIONS_BASE}/{sid}/status",
            params={"new_status": "archived"},
            headers=api_key_headers,
        )
        assert response.status_code == 422

        body = response.json()
        assert body["success"] is False
        assert "archived" in body["message"]

    def test_update_status_invalid_transition(
        self, client, api_key_headers, created_submission
    ):
        """Cannot skip open → complete directly."""
        sid = created_submission["submission_id"]
        response = client.patch(
            f"{SUBMISSIONS_BASE}/{sid}/status",
            params={"new_status": "complete"},
            headers=api_key_headers,
        )
        assert response.status_code == 422

        body = response.json()
        assert body["success"] is False
        assert "Cannot transition" in body["message"]

    def test_update_status_terminal_state_complete(
        self, client, api_key_headers, created_submission
    ):
        """complete is a terminal state — no further transitions."""
        sid = created_submission["submission_id"]
        client.patch(
            f"{SUBMISSIONS_BASE}/{sid}/status",
            params={"new_status": "in_progress"},
            headers=api_key_headers,
        )
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

    def test_update_status_404_nonexistent(self, client, api_key_headers):
        response = client.patch(
            f"{SUBMISSIONS_BASE}/sub_doesnotexist/status",
            params={"new_status": "in_progress"},
            headers=api_key_headers,
        )
        assert response.status_code == 404

    def test_update_status_requires_authentication(self, client, created_submission):
        sid = created_submission["submission_id"]
        response = client.patch(
            f"{SUBMISSIONS_BASE}/{sid}/status",
            params={"new_status": "in_progress"},
        )
        assert response.status_code == 401
