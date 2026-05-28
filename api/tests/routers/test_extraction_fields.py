"""
Tests for per-document extraction field configuration and process rules.

Covers:
  GET  /v1/processes/{pid}/fields/summary
  POST /v1/processes/{pid}/documents/{did}/fields
  GET  /v1/processes/{pid}/documents/{did}/fields
  GET  /v1/processes/{pid}/documents/{did}/fields/{fid}
  PATCH /v1/processes/{pid}/documents/{did}/fields/{fid}
  DELETE /v1/processes/{pid}/documents/{did}/fields/{fid}
  GET  /v1/processes/{pid}/rules
  POST /v1/processes/{pid}/rules
"""

import pytest


# ── Fixtures ───────────────────────────────────────────────────────────────
@pytest.fixture
def process_with_doc(client, api_key_headers):
    """Create a process with one document and return both IDs."""
    resp = client.post(
        "/v1/processes",
        json={
            "name": "Field Test Process",
            "documents": [
                {"name": "NIN Slip", "category": "Identity", "is_required": True}
            ],
        },
        headers=api_key_headers,
    )
    assert resp.status_code == 201
    data = resp.json()["data"]
    process_id = data["process_id"]
    doc_id = data["documents"][0]["id"]
    return {"process_id": process_id, "doc_id": doc_id}


@pytest.fixture
def field_in_doc(client, api_key_headers, process_with_doc):
    """Add a field to the document and return its ID."""
    pid = process_with_doc["process_id"]
    did = process_with_doc["doc_id"]
    resp = client.post(
        f"/v1/processes/{pid}/documents/{did}/fields",
        json={
            "name": "Full Name",
            "description": "Legal name",
            "include_in_decision": True,
            "null_is_manual": True,
            "sort_order": 0,
        },
        headers=api_key_headers,
    )
    assert resp.status_code == 201
    return {
        **process_with_doc,
        "field_id": resp.json()["data"]["id"],
    }


# ── GET /v1/processes/{pid}/fields/summary ────────────────────────────────
class TestFieldsSummary:
    def test_summary_returns_200(self, client, api_key_headers, process_with_doc):
        pid = process_with_doc["process_id"]
        resp = client.get(
            f"/v1/processes/{pid}/fields/summary",
            headers=api_key_headers,
        )
        assert resp.status_code == 200

    def test_summary_response_envelope(self, client, api_key_headers, process_with_doc):
        pid = process_with_doc["process_id"]
        resp = client.get(
            f"/v1/processes/{pid}/fields/summary",
            headers=api_key_headers,
        )
        body = resp.json()
        assert body["success"] is True
        assert "data" in body

    def test_summary_extraction_disabled_when_no_fields(
        self, client, api_key_headers, process_with_doc
    ):
        pid = process_with_doc["process_id"]
        resp = client.get(
            f"/v1/processes/{pid}/fields/summary",
            headers=api_key_headers,
        )
        data = resp.json()["data"]
        assert data["extraction_enabled"] is False
        assert data["documents_without_fields"] == 1

    def test_summary_extraction_enabled_after_adding_field(
        self, client, api_key_headers, field_in_doc
    ):
        pid = field_in_doc["process_id"]
        resp = client.get(
            f"/v1/processes/{pid}/fields/summary",
            headers=api_key_headers,
        )
        data = resp.json()["data"]
        assert data["extraction_enabled"] is True
        assert data["documents_with_fields"] == 1

    def test_summary_includes_document_list(
        self, client, api_key_headers, process_with_doc
    ):
        pid = process_with_doc["process_id"]
        resp = client.get(
            f"/v1/processes/{pid}/fields/summary",
            headers=api_key_headers,
        )
        data = resp.json()["data"]
        assert "documents" in data
        assert len(data["documents"]) == 1
        assert data["documents"][0]["document_name"] == "NIN Slip"

    def test_summary_404_nonexistent_process(self, client, api_key_headers):
        resp = client.get(
            "/v1/processes/proc_doesnotexist/fields/summary",
            headers=api_key_headers,
        )
        assert resp.status_code == 404

    def test_summary_requires_authentication(self, client, process_with_doc):
        pid = process_with_doc["process_id"]
        resp = client.get(f"/v1/processes/{pid}/fields/summary")
        assert resp.status_code == 401


# ── POST /v1/processes/{pid}/documents/{did}/fields ───────────────────────
class TestAddDocumentField:
    def test_add_returns_201(self, client, api_key_headers, process_with_doc):
        pid = process_with_doc["process_id"]
        did = process_with_doc["doc_id"]
        resp = client.post(
            f"/v1/processes/{pid}/documents/{did}/fields",
            json={"name": "NIN", "include_in_decision": True, "null_is_manual": True},
            headers=api_key_headers,
        )
        assert resp.status_code == 201

    def test_add_response_envelope(self, client, api_key_headers, process_with_doc):
        pid = process_with_doc["process_id"]
        did = process_with_doc["doc_id"]
        resp = client.post(
            f"/v1/processes/{pid}/documents/{did}/fields",
            json={"name": "NIN"},
            headers=api_key_headers,
        )
        body = resp.json()
        assert body["success"] is True
        assert "id" in body["data"]

    def test_add_stores_field_name(self, client, api_key_headers, process_with_doc):
        pid = process_with_doc["process_id"]
        did = process_with_doc["doc_id"]
        resp = client.post(
            f"/v1/processes/{pid}/documents/{did}/fields",
            json={"name": "Date of Birth"},
            headers=api_key_headers,
        )
        assert resp.json()["data"]["name"] == "Date of Birth"

    def test_add_field_id_has_correct_prefix(
        self, client, api_key_headers, process_with_doc
    ):
        pid = process_with_doc["process_id"]
        did = process_with_doc["doc_id"]
        resp = client.post(
            f"/v1/processes/{pid}/documents/{did}/fields",
            json={"name": "Address"},
            headers=api_key_headers,
        )
        assert resp.json()["data"]["id"].startswith("pdf_")

    def test_add_rejects_duplicate_name(self, client, api_key_headers, field_in_doc):
        pid = field_in_doc["process_id"]
        did = field_in_doc["doc_id"]
        resp = client.post(
            f"/v1/processes/{pid}/documents/{did}/fields",
            json={"name": "Full Name"},
            headers=api_key_headers,
        )
        assert resp.status_code == 409

    def test_same_name_allowed_on_different_documents(
        self, client, api_key_headers, process_with_doc
    ):
        """Full Name can appear on both NIN Slip and Bank Statement."""
        pid = process_with_doc["process_id"]
        # Add second document
        update = client.patch(
            f"/v1/processes/{pid}",
            json={
                "documents": [
                    {"name": "NIN Slip", "category": "Identity", "is_required": True},
                    {
                        "name": "Bank Statement",
                        "category": "Financial",
                        "is_required": True,
                    },
                ]
            },
            headers=api_key_headers,
        )
        docs = update.json()["data"]["documents"]
        did1 = docs[0]["id"]
        did2 = docs[1]["id"]

        resp1 = client.post(
            f"/v1/processes/{pid}/documents/{did1}/fields",
            json={"name": "Full Name"},
            headers=api_key_headers,
        )
        resp2 = client.post(
            f"/v1/processes/{pid}/documents/{did2}/fields",
            json={"name": "Full Name"},
            headers=api_key_headers,
        )
        assert resp1.status_code == 201
        assert resp2.status_code == 201

    def test_add_404_nonexistent_document(
        self, client, api_key_headers, process_with_doc
    ):
        pid = process_with_doc["process_id"]
        resp = client.post(
            f"/v1/processes/{pid}/documents/99999/fields",
            json={"name": "Full Name"},
            headers=api_key_headers,
        )
        assert resp.status_code == 404

    def test_add_requires_authentication(self, client, process_with_doc):
        pid = process_with_doc["process_id"]
        did = process_with_doc["doc_id"]
        resp = client.post(
            f"/v1/processes/{pid}/documents/{did}/fields",
            json={"name": "Full Name"},
        )
        assert resp.status_code == 401


# ── GET /v1/processes/{pid}/documents/{did}/fields ────────────────────────
class TestListDocumentFields:
    def test_list_returns_200(self, client, api_key_headers, process_with_doc):
        pid = process_with_doc["process_id"]
        did = process_with_doc["doc_id"]
        resp = client.get(
            f"/v1/processes/{pid}/documents/{did}/fields",
            headers=api_key_headers,
        )
        assert resp.status_code == 200

    def test_list_empty_for_new_document(
        self, client, api_key_headers, process_with_doc
    ):
        pid = process_with_doc["process_id"]
        did = process_with_doc["doc_id"]
        resp = client.get(
            f"/v1/processes/{pid}/documents/{did}/fields",
            headers=api_key_headers,
        )
        data = resp.json()["data"]
        assert data["total"] == 0
        assert data["fields_configured"] is False

    def test_list_includes_added_field(self, client, api_key_headers, field_in_doc):
        pid = field_in_doc["process_id"]
        did = field_in_doc["doc_id"]
        resp = client.get(
            f"/v1/processes/{pid}/documents/{did}/fields",
            headers=api_key_headers,
        )
        data = resp.json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["name"] == "Full Name"

    def test_list_includes_document_name(self, client, api_key_headers, field_in_doc):
        pid = field_in_doc["process_id"]
        did = field_in_doc["doc_id"]
        resp = client.get(
            f"/v1/processes/{pid}/documents/{did}/fields",
            headers=api_key_headers,
        )
        assert resp.json()["data"]["document_name"] == "NIN Slip"

    def test_list_requires_authentication(self, client, process_with_doc):
        pid = process_with_doc["process_id"]
        did = process_with_doc["doc_id"]
        resp = client.get(f"/v1/processes/{pid}/documents/{did}/fields")
        assert resp.status_code == 401


# ── GET /v1/processes/{pid}/documents/{did}/fields/{fid} ──────────────────
class TestGetDocumentField:
    def test_get_returns_200(self, client, api_key_headers, field_in_doc):
        pid = field_in_doc["process_id"]
        did = field_in_doc["doc_id"]
        fid = field_in_doc["field_id"]
        resp = client.get(
            f"/v1/processes/{pid}/documents/{did}/fields/{fid}",
            headers=api_key_headers,
        )
        assert resp.status_code == 200

    def test_get_returns_correct_field(self, client, api_key_headers, field_in_doc):
        pid = field_in_doc["process_id"]
        did = field_in_doc["doc_id"]
        fid = field_in_doc["field_id"]
        resp = client.get(
            f"/v1/processes/{pid}/documents/{did}/fields/{fid}",
            headers=api_key_headers,
        )
        data = resp.json()["data"]
        assert data["id"] == fid
        assert data["name"] == "Full Name"

    def test_get_404_nonexistent_field(self, client, api_key_headers, field_in_doc):
        pid = field_in_doc["process_id"]
        did = field_in_doc["doc_id"]
        resp = client.get(
            f"/v1/processes/{pid}/documents/{did}/fields/pdf_doesnotexist",
            headers=api_key_headers,
        )
        assert resp.status_code == 404


# ── PATCH /v1/processes/{pid}/documents/{did}/fields/{fid} ────────────────
class TestUpdateDocumentField:
    def test_update_returns_200(self, client, api_key_headers, field_in_doc):
        pid = field_in_doc["process_id"]
        did = field_in_doc["doc_id"]
        fid = field_in_doc["field_id"]
        resp = client.patch(
            f"/v1/processes/{pid}/documents/{did}/fields/{fid}",
            json={"is_active": False},
            headers=api_key_headers,
        )
        assert resp.status_code == 200

    def test_update_disables_field(self, client, api_key_headers, field_in_doc):
        pid = field_in_doc["process_id"]
        did = field_in_doc["doc_id"]
        fid = field_in_doc["field_id"]
        resp = client.patch(
            f"/v1/processes/{pid}/documents/{did}/fields/{fid}",
            json={"is_active": False},
            headers=api_key_headers,
        )
        assert resp.json()["data"]["is_active"] is False

    def test_update_null_is_manual(self, client, api_key_headers, field_in_doc):
        pid = field_in_doc["process_id"]
        did = field_in_doc["doc_id"]
        fid = field_in_doc["field_id"]
        resp = client.patch(
            f"/v1/processes/{pid}/documents/{did}/fields/{fid}",
            json={"null_is_manual": False},
            headers=api_key_headers,
        )
        assert resp.json()["data"]["null_is_manual"] is False

    def test_update_persists(self, client, api_key_headers, field_in_doc):
        pid = field_in_doc["process_id"]
        did = field_in_doc["doc_id"]
        fid = field_in_doc["field_id"]
        client.patch(
            f"/v1/processes/{pid}/documents/{did}/fields/{fid}",
            json={"is_active": False},
            headers=api_key_headers,
        )
        resp = client.get(
            f"/v1/processes/{pid}/documents/{did}/fields/{fid}",
            headers=api_key_headers,
        )
        assert resp.json()["data"]["is_active"] is False

    def test_update_requires_authentication(self, client, field_in_doc):
        pid = field_in_doc["process_id"]
        did = field_in_doc["doc_id"]
        fid = field_in_doc["field_id"]
        resp = client.patch(
            f"/v1/processes/{pid}/documents/{did}/fields/{fid}",
            json={"is_active": False},
        )
        assert resp.status_code == 401


# ── DELETE /v1/processes/{pid}/documents/{did}/fields/{fid} ───────────────
class TestDeleteDocumentField:
    def test_delete_returns_200(self, client, api_key_headers, field_in_doc):
        pid = field_in_doc["process_id"]
        did = field_in_doc["doc_id"]
        fid = field_in_doc["field_id"]
        resp = client.delete(
            f"/v1/processes/{pid}/documents/{did}/fields/{fid}",
            headers=api_key_headers,
        )
        assert resp.status_code == 200

    def test_delete_removes_field(self, client, api_key_headers, field_in_doc):
        pid = field_in_doc["process_id"]
        did = field_in_doc["doc_id"]
        fid = field_in_doc["field_id"]
        client.delete(
            f"/v1/processes/{pid}/documents/{did}/fields/{fid}",
            headers=api_key_headers,
        )
        resp = client.get(
            f"/v1/processes/{pid}/documents/{did}/fields/{fid}",
            headers=api_key_headers,
        )
        assert resp.status_code == 404

    def test_delete_disables_extraction_when_last_field(
        self, client, api_key_headers, field_in_doc
    ):
        pid = field_in_doc["process_id"]
        did = field_in_doc["doc_id"]
        fid = field_in_doc["field_id"]
        client.delete(
            f"/v1/processes/{pid}/documents/{did}/fields/{fid}",
            headers=api_key_headers,
        )
        summary = client.get(
            f"/v1/processes/{pid}/fields/summary",
            headers=api_key_headers,
        )
        assert summary.json()["data"]["extraction_enabled"] is False

    def test_delete_requires_authentication(self, client, field_in_doc):
        pid = field_in_doc["process_id"]
        did = field_in_doc["doc_id"]
        fid = field_in_doc["field_id"]
        resp = client.delete(f"/v1/processes/{pid}/documents/{did}/fields/{fid}")
        assert resp.status_code == 401


# ── GET /v1/processes/{pid}/rules ─────────────────────────────────────────
class TestListProcessRules:
    def test_list_returns_200(self, client, api_key_headers, process_with_doc):
        pid = process_with_doc["process_id"]
        resp = client.get(
            f"/v1/processes/{pid}/rules",
            headers=api_key_headers,
        )
        assert resp.status_code == 200

    def test_list_includes_global_rules(
        self, client, api_key_headers, process_with_doc
    ):
        # Create a global rule first (no process_id)
        client.post(
            "/v1/config/rules",
            json={
                "name": "Global rule for test",
                "rule_type": "required",
                "field": "Full Name",
                "severity": "error",
            },
            headers=api_key_headers,
        )
        pid = process_with_doc["process_id"]
        resp = client.get(
            f"/v1/processes/{pid}/rules",
            headers=api_key_headers,
        )
        data = resp.json()["data"]
        assert data["global_count"] > 0

    def test_list_response_has_required_fields(
        self, client, api_key_headers, process_with_doc
    ):
        pid = process_with_doc["process_id"]
        resp = client.get(
            f"/v1/processes/{pid}/rules",
            headers=api_key_headers,
        )
        data = resp.json()["data"]
        assert "items" in data
        assert "total" in data
        assert "global_count" in data
        assert "process_count" in data

    def test_list_404_nonexistent_process(self, client, api_key_headers):
        resp = client.get(
            "/v1/processes/proc_doesnotexist/rules",
            headers=api_key_headers,
        )
        assert resp.status_code == 404

    def test_list_requires_authentication(self, client, process_with_doc):
        pid = process_with_doc["process_id"]
        resp = client.get(f"/v1/processes/{pid}/rules")
        assert resp.status_code == 401


# ── POST /v1/processes/{pid}/rules ────────────────────────────────────────
class TestCreateProcessRule:
    def test_create_returns_201(self, client, api_key_headers, process_with_doc):
        pid = process_with_doc["process_id"]
        resp = client.post(
            f"/v1/processes/{pid}/rules",
            json={
                "name": "Property value required",
                "rule_type": "required",
                "field": "Property Value",
                "severity": "error",
            },
            headers=api_key_headers,
        )
        assert resp.status_code == 201

    def test_create_scope_is_process(self, client, api_key_headers, process_with_doc):
        pid = process_with_doc["process_id"]
        resp = client.post(
            f"/v1/processes/{pid}/rules",
            json={
                "name": "Mortgage amount required",
                "rule_type": "required",
                "field": "Mortgage Amount",
            },
            headers=api_key_headers,
        )
        assert resp.json()["data"]["scope"] == "process"

    def test_create_process_id_matches(self, client, api_key_headers, process_with_doc):
        pid = process_with_doc["process_id"]
        resp = client.post(
            f"/v1/processes/{pid}/rules",
            json={
                "name": "Property address required",
                "rule_type": "required",
                "field": "Property Address",
            },
            headers=api_key_headers,
        )
        assert resp.json()["data"]["process_id"] == pid

    def test_create_rule_appears_in_process_rules(
        self, client, api_key_headers, process_with_doc
    ):
        pid = process_with_doc["process_id"]
        client.post(
            f"/v1/processes/{pid}/rules",
            json={
                "name": "Unique process rule xyz",
                "rule_type": "required",
                "field": "Some Field",
            },
            headers=api_key_headers,
        )
        resp = client.get(
            f"/v1/processes/{pid}/rules",
            headers=api_key_headers,
        )
        names = [r["name"] for r in resp.json()["data"]["items"]]
        assert "Unique process rule xyz" in names

    def test_create_process_count_increments(
        self, client, api_key_headers, process_with_doc
    ):
        pid = process_with_doc["process_id"]
        before = client.get(
            f"/v1/processes/{pid}/rules", headers=api_key_headers
        ).json()["data"]["process_count"]

        client.post(
            f"/v1/processes/{pid}/rules",
            json={
                "name": "Another process rule",
                "rule_type": "required",
                "field": "Another Field",
            },
            headers=api_key_headers,
        )

        after = client.get(
            f"/v1/processes/{pid}/rules", headers=api_key_headers
        ).json()["data"]["process_count"]

        assert after == before + 1

    def test_create_rejects_duplicate_name(
        self, client, api_key_headers, process_with_doc
    ):
        pid = process_with_doc["process_id"]
        payload = {
            "name": "Duplicate rule name",
            "rule_type": "required",
            "field": "Some Field",
        }
        client.post(f"/v1/processes/{pid}/rules", json=payload, headers=api_key_headers)
        resp = client.post(
            f"/v1/processes/{pid}/rules", json=payload, headers=api_key_headers
        )
        assert resp.status_code == 422

    def test_create_404_nonexistent_process(self, client, api_key_headers):
        resp = client.post(
            "/v1/processes/proc_doesnotexist/rules",
            json={
                "name": "Some rule",
                "rule_type": "required",
                "field": "Some Field",
            },
            headers=api_key_headers,
        )
        assert resp.status_code == 404

    def test_create_requires_authentication(self, client, process_with_doc):
        pid = process_with_doc["process_id"]
        resp = client.post(
            f"/v1/processes/{pid}/rules",
            json={
                "name": "No auth rule",
                "rule_type": "required",
                "field": "Field",
            },
        )
        assert resp.status_code == 401
