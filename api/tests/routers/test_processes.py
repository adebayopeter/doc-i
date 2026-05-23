"""
Tests for POST, GET, DELETE /v1/processes
"""

import pytest

BASE = "/v1/processes"


# ── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture
def sample_payload():
    """Valid process creation payload."""
    return {
        "name": "RSA Mortgage",
        "description": "Residential mortgage application",
        "color_var": "info",
        "icon": "ti-home-2",
        "documents": [
            {"name": "National ID / NIN slip", "category": "Identity"},
            {"name": "Bank statement (6 months)", "category": "Financial"},
            {"name": "Offer letter", "category": "Income", "is_required": False},
        ],
    }


@pytest.fixture
def created_process(client, api_key_headers, sample_payload):
    """Creates a process and returns the response data."""
    response = client.post(BASE, json=sample_payload, headers=api_key_headers)
    assert response.status_code == 201
    return response.json()["data"]


# ── POST /v1/processes ─────────────────────────────────────────────────────


class TestCreateProcess:
    def test_create_returns_201(self, client, api_key_headers, sample_payload):
        response = client.post(BASE, json=sample_payload, headers=api_key_headers)
        assert response.status_code == 201

    def test_create_response_envelope(self, client, api_key_headers, sample_payload):
        response = client.post(BASE, json=sample_payload, headers=api_key_headers)
        body = response.json()

        assert body["success"] is True
        assert body["message"] == "Process created successfully"
        assert body["data"] is not None

    def test_create_returns_process_id(self, client, api_key_headers, sample_payload):
        response = client.post(BASE, json=sample_payload, headers=api_key_headers)
        data = response.json()["data"]

        assert "process_id" in data
        assert data["process_id"].startswith("proc_")

    def test_create_stores_all_fields(self, client, api_key_headers, sample_payload):
        response = client.post(BASE, json=sample_payload, headers=api_key_headers)
        data = response.json()["data"]

        assert data["name"] == "RSA Mortgage"
        assert data["description"] == "Residential mortgage application"
        assert data["color_var"] == "info"
        assert data["icon"] == "ti-home-2"

    def test_create_stores_documents(self, client, api_key_headers, sample_payload):
        response = client.post(BASE, json=sample_payload, headers=api_key_headers)
        data = response.json()["data"]

        assert data["document_count"] == 3
        assert len(data["documents"]) == 3

    def test_create_documents_have_correct_fields(
        self, client, api_key_headers, sample_payload
    ):
        response = client.post(BASE, json=sample_payload, headers=api_key_headers)
        documents = response.json()["data"]["documents"]

        first_doc = documents[0]
        assert first_doc["name"] == "National ID / NIN slip"
        assert first_doc["category"] == "Identity"
        assert first_doc["is_required"] is True
        assert first_doc["sort_order"] == 0

    def test_create_optional_document_is_not_required(
        self, client, api_key_headers, sample_payload
    ):
        response = client.post(BASE, json=sample_payload, headers=api_key_headers)
        documents = response.json()["data"]["documents"]

        offer_letter = next(d for d in documents if d["name"] == "Offer letter")
        assert offer_letter["is_required"] is False

    def test_create_documents_sorted_by_order(
        self, client, api_key_headers, sample_payload
    ):
        response = client.post(BASE, json=sample_payload, headers=api_key_headers)
        documents = response.json()["data"]["documents"]

        orders = [d["sort_order"] for d in documents]
        assert orders == sorted(orders)

    def test_create_requires_authentication(self, client, sample_payload):
        response = client.post(BASE, json=sample_payload)
        assert response.status_code == 401

    def test_create_rejects_invalid_api_key(self, client, sample_payload):
        response = client.post(
            BASE, json=sample_payload, headers={"X-API-Key": "wrong-key"}
        )
        assert response.status_code == 401

    def test_create_requires_name(self, client, api_key_headers):
        response = client.post(
            BASE,
            json={"documents": [{"name": "NIN slip", "category": "Identity"}]},
            headers=api_key_headers,
        )
        assert response.status_code == 422

    def test_create_requires_at_least_one_document(self, client, api_key_headers):
        response = client.post(
            BASE,
            json={"name": "Empty Process", "documents": []},
            headers=api_key_headers,
        )
        assert response.status_code == 422

    def test_create_rejects_duplicate_name(
        self, client, api_key_headers, sample_payload
    ):
        # First creation
        client.post(BASE, json=sample_payload, headers=api_key_headers)

        # Duplicate
        response = client.post(BASE, json=sample_payload, headers=api_key_headers)
        assert response.status_code == 409

        body = response.json()
        assert body["success"] is False
        assert "already exists" in body["message"]

    def test_create_duplicate_returns_existing_id(
        self, client, api_key_headers, sample_payload
    ):
        first = client.post(BASE, json=sample_payload, headers=api_key_headers)
        first_id = first.json()["data"]["process_id"]

        second = client.post(BASE, json=sample_payload, headers=api_key_headers)
        assert second.json()["data"]["existing_process_id"] == first_id

    def test_create_name_too_short(self, client, api_key_headers):
        response = client.post(
            BASE,
            json={
                "name": "A",
                "documents": [{"name": "NIN slip", "category": "Identity"}],
            },
            headers=api_key_headers,
        )
        assert response.status_code == 422


# ── GET /v1/processes ──────────────────────────────────────────────────────


class TestListProcesses:
    def test_list_returns_200(self, client, api_key_headers):
        response = client.get(BASE, headers=api_key_headers)
        assert response.status_code == 200

    def test_list_response_envelope(self, client, api_key_headers):
        response = client.get(BASE, headers=api_key_headers)
        body = response.json()

        assert body["success"] is True
        assert body["message"] == "Processes retrieved successfully"
        assert body["data"] is not None

    def test_list_returns_items_and_total(self, client, api_key_headers):
        response = client.get(BASE, headers=api_key_headers)
        data = response.json()["data"]

        assert "items" in data
        assert "total" in data

    def test_list_includes_created_process(
        self, client, api_key_headers, created_process
    ):
        response = client.get(BASE, headers=api_key_headers)
        data = response.json()["data"]

        process_ids = [p["process_id"] for p in data["items"]]
        assert created_process["process_id"] in process_ids

    def test_list_total_matches_items_count(
        self, client, api_key_headers, created_process
    ):
        response = client.get(BASE, headers=api_key_headers)
        data = response.json()["data"]

        assert data["total"] == len(data["items"])

    def test_list_requires_authentication(self, client):
        response = client.get(BASE)
        assert response.status_code == 401

    def test_list_does_not_include_deactivated_process(
        self, client, api_key_headers, created_process
    ):
        process_id = created_process["process_id"]

        # Deactivate
        client.delete(f"{BASE}/{process_id}", headers=api_key_headers)

        response = client.get(BASE, headers=api_key_headers)
        process_ids = [p["process_id"] for p in response.json()["data"]["items"]]
        assert process_id not in process_ids


# ── GET /v1/processes/{process_id} ────────────────────────────────────────


class TestGetProcess:
    def test_get_returns_200(self, client, api_key_headers, created_process):
        process_id = created_process["process_id"]
        response = client.get(f"{BASE}/{process_id}", headers=api_key_headers)
        assert response.status_code == 200

    def test_get_response_envelope(self, client, api_key_headers, created_process):
        process_id = created_process["process_id"]
        response = client.get(f"{BASE}/{process_id}", headers=api_key_headers)
        body = response.json()

        assert body["success"] is True
        assert body["message"] == "Process retrieved successfully"

    def test_get_returns_full_checklist(self, client, api_key_headers, created_process):
        process_id = created_process["process_id"]
        response = client.get(f"{BASE}/{process_id}", headers=api_key_headers)
        data = response.json()["data"]

        assert "documents" in data
        assert len(data["documents"]) == 3

    def test_get_returns_correct_data(self, client, api_key_headers, created_process):
        process_id = created_process["process_id"]
        response = client.get(f"{BASE}/{process_id}", headers=api_key_headers)
        data = response.json()["data"]

        assert data["process_id"] == process_id
        assert data["name"] == "RSA Mortgage"

    def test_get_nonexistent_process(self, client, api_key_headers):
        response = client.get(f"{BASE}/proc_doesnotexist", headers=api_key_headers)
        assert response.status_code == 404

        body = response.json()
        assert body["success"] is False
        assert body["message"] == "Process not found"

    def test_get_requires_authentication(self, client, created_process):
        process_id = created_process["process_id"]
        response = client.get(f"{BASE}/{process_id}")
        assert response.status_code == 401


# ── DELETE /v1/processes/{process_id} ────────────────────────────────────


class TestDeleteProcess:
    def test_delete_returns_200(self, client, api_key_headers, created_process):
        process_id = created_process["process_id"]
        response = client.delete(f"{BASE}/{process_id}", headers=api_key_headers)
        assert response.status_code == 200

    def test_delete_response_envelope(self, client, api_key_headers, created_process):
        process_id = created_process["process_id"]
        response = client.delete(f"{BASE}/{process_id}", headers=api_key_headers)
        body = response.json()

        assert body["success"] is True
        assert body["message"] == "Process deactivated successfully"
        assert body["data"]["process_id"] == process_id

    def test_delete_is_soft_delete(self, client, api_key_headers, created_process):
        """Deleted process must return 404 on subsequent GET."""
        process_id = created_process["process_id"]
        client.delete(f"{BASE}/{process_id}", headers=api_key_headers)

        response = client.get(f"{BASE}/{process_id}", headers=api_key_headers)
        assert response.status_code == 404

    def test_delete_nonexistent_process(self, client, api_key_headers):
        response = client.delete(f"{BASE}/proc_doesnotexist", headers=api_key_headers)
        assert response.status_code == 404

    def test_delete_requires_authentication(self, client, created_process):
        process_id = created_process["process_id"]
        response = client.delete(f"{BASE}/{process_id}")
        assert response.status_code == 401
