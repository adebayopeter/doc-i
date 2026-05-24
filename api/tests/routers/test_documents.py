"""
Tests for /v1/documents endpoints.
"""

import io

import pytest

DOCUMENTS_BASE = "/v1/documents"
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
def pdf_file():
    """Minimal valid PDF bytes."""
    content = b"%PDF-1.4 minimal test document"
    return ("test_document.pdf", io.BytesIO(content), "application/pdf")


@pytest.fixture
def png_file():
    """Minimal PNG-like bytes."""
    content = b"\x89PNG\r\n\x1a\nminimal test png"
    return ("test_image.png", io.BytesIO(content), "image/png")


@pytest.fixture
def uploaded_document(client, api_key_headers, created_submission, pdf_file):
    """Upload a document and return the response data."""
    sid = created_submission["submission_id"]
    filename, content, mime = pdf_file
    response = client.post(
        f"{DOCUMENTS_BASE}/submissions/{sid}/upload",
        files={"file": (filename, content, mime)},
        headers=api_key_headers,
    )
    assert response.status_code == 202
    return response.json()["data"]


# ── POST /v1/documents/submissions/{submission_id}/upload ─────────────────


class TestUploadDocument:
    def test_upload_returns_202(
        self, client, api_key_headers, created_submission, pdf_file
    ):
        sid = created_submission["submission_id"]
        filename, content, mime = pdf_file
        response = client.post(
            f"{DOCUMENTS_BASE}/submissions/{sid}/upload",
            files={"file": (filename, content, mime)},
            headers=api_key_headers,
        )
        assert response.status_code == 202

    def test_upload_response_envelope(
        self, client, api_key_headers, created_submission, pdf_file
    ):
        sid = created_submission["submission_id"]
        filename, content, mime = pdf_file
        response = client.post(
            f"{DOCUMENTS_BASE}/submissions/{sid}/upload",
            files={"file": (filename, content, mime)},
            headers=api_key_headers,
        )
        body = response.json()

        assert body["success"] is True
        assert "Classification is running" in body["message"]
        assert body["data"] is not None

    def test_upload_returns_document_id(
        self, client, api_key_headers, created_submission, pdf_file
    ):
        sid = created_submission["submission_id"]
        filename, content, mime = pdf_file
        response = client.post(
            f"{DOCUMENTS_BASE}/submissions/{sid}/upload",
            files={"file": (filename, content, mime)},
            headers=api_key_headers,
        )
        data = response.json()["data"]

        assert "document_id" in data
        assert data["document_id"].startswith("doc_")

    def test_upload_stores_correct_fields(
        self, client, api_key_headers, created_submission, pdf_file
    ):
        sid = created_submission["submission_id"]
        filename, content, mime = pdf_file
        response = client.post(
            f"{DOCUMENTS_BASE}/submissions/{sid}/upload",
            files={"file": (filename, content, mime)},
            headers=api_key_headers,
        )
        data = response.json()["data"]

        assert data["submission_id"] == sid
        assert data["filename"] == "test_document.pdf"
        assert data["mime_type"] == "application/pdf"
        assert data["status"] == "uploaded"

    def test_upload_sets_submission_in_progress(
        self, client, api_key_headers, created_submission, pdf_file
    ):
        """Uploading first document moves submission from open to in_progress."""
        sid = created_submission["submission_id"]
        assert created_submission["status"] == "open"

        filename, content, mime = pdf_file
        client.post(
            f"{DOCUMENTS_BASE}/submissions/{sid}/upload",
            files={"file": (filename, content, mime)},
            headers=api_key_headers,
        )

        response = client.get(f"{SUBMISSIONS_BASE}/{sid}", headers=api_key_headers)
        assert response.json()["data"]["status"] == "in_progress"

    def test_upload_accepts_png(
        self, client, api_key_headers, created_submission, png_file
    ):
        sid = created_submission["submission_id"]
        filename, content, mime = png_file
        response = client.post(
            f"{DOCUMENTS_BASE}/submissions/{sid}/upload",
            files={"file": (filename, content, mime)},
            headers=api_key_headers,
        )
        assert response.status_code == 202

    def test_upload_rejects_unsupported_type(
        self, client, api_key_headers, created_submission
    ):
        sid = created_submission["submission_id"]
        response = client.post(
            f"{DOCUMENTS_BASE}/submissions/{sid}/upload",
            files={"file": ("doc.txt", io.BytesIO(b"text content"), "text/plain")},
            headers=api_key_headers,
        )
        assert response.status_code == 400

        body = response.json()
        assert body["success"] is False
        assert "Unsupported file type" in body["message"]

    def test_upload_rejects_empty_file(
        self, client, api_key_headers, created_submission
    ):
        sid = created_submission["submission_id"]
        response = client.post(
            f"{DOCUMENTS_BASE}/submissions/{sid}/upload",
            files={"file": ("empty.pdf", io.BytesIO(b""), "application/pdf")},
            headers=api_key_headers,
        )
        assert response.status_code == 400

        body = response.json()
        assert body["success"] is False
        assert "empty" in body["message"].lower()

    def test_upload_to_nonexistent_submission(self, client, api_key_headers, pdf_file):
        filename, content, mime = pdf_file
        response = client.post(
            f"{DOCUMENTS_BASE}/submissions/sub_doesnotexist/upload",
            files={"file": (filename, content, mime)},
            headers=api_key_headers,
        )
        assert response.status_code == 404

        body = response.json()
        assert body["success"] is False
        assert "Submission not found" in body["message"]

    def test_upload_to_complete_submission_rejected(
        self, client, api_key_headers, created_submission, pdf_file
    ):
        sid = created_submission["submission_id"]

        # Progress to complete
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

        filename, content, mime = pdf_file
        response = client.post(
            f"{DOCUMENTS_BASE}/submissions/{sid}/upload",
            files={"file": (filename, content, mime)},
            headers=api_key_headers,
        )
        assert response.status_code == 422

        body = response.json()
        assert body["success"] is False
        assert "complete" in body["message"]

    def test_upload_multiple_documents(
        self, client, api_key_headers, created_submission, pdf_file
    ):
        """Same submission can receive multiple documents."""
        sid = created_submission["submission_id"]
        results = []
        for i in range(3):
            filename, _, mime = pdf_file
            response = client.post(
                f"{DOCUMENTS_BASE}/submissions/{sid}/upload",
                files={
                    "file": (
                        f"document_{i}.pdf",
                        io.BytesIO(b"%PDF-1.4 test"),
                        mime,
                    )
                },
                headers=api_key_headers,
            )
            assert response.status_code == 202
            results.append(response.json()["data"]["document_id"])

        assert len(set(results)) == 3  # all unique IDs

    def test_upload_requires_authentication(self, client, created_submission, pdf_file):
        sid = created_submission["submission_id"]
        filename, content, mime = pdf_file
        response = client.post(
            f"{DOCUMENTS_BASE}/submissions/{sid}/upload",
            files={"file": (filename, content, mime)},
        )
        assert response.status_code == 401


# ── GET /v1/documents/{document_id} ───────────────────────────────────────


class TestGetDocument:
    def test_get_returns_200(self, client, api_key_headers, uploaded_document):
        doc_id = uploaded_document["document_id"]
        response = client.get(f"{DOCUMENTS_BASE}/{doc_id}", headers=api_key_headers)
        assert response.status_code == 200

    def test_get_response_envelope(self, client, api_key_headers, uploaded_document):
        doc_id = uploaded_document["document_id"]
        response = client.get(f"{DOCUMENTS_BASE}/{doc_id}", headers=api_key_headers)
        body = response.json()

        assert body["success"] is True
        assert body["message"] == "Document retrieved successfully"
        assert body["data"] is not None

    def test_get_returns_correct_document(
        self, client, api_key_headers, uploaded_document
    ):
        doc_id = uploaded_document["document_id"]
        response = client.get(f"{DOCUMENTS_BASE}/{doc_id}", headers=api_key_headers)
        data = response.json()["data"]

        assert data["document_id"] == doc_id
        assert data["filename"] == "test_document.pdf"
        assert data["mime_type"] == "application/pdf"

    def test_get_returns_status(self, client, api_key_headers, uploaded_document):
        doc_id = uploaded_document["document_id"]
        response = client.get(f"{DOCUMENTS_BASE}/{doc_id}", headers=api_key_headers)
        data = response.json()["data"]

        # Status will be 'uploaded' since Celery is not running in tests
        assert data["status"] in {"uploaded", "processing", "classified", "failed"}

    def test_get_nonexistent_document(self, client, api_key_headers):
        response = client.get(
            f"{DOCUMENTS_BASE}/doc_doesnotexist", headers=api_key_headers
        )
        assert response.status_code == 404

        body = response.json()
        assert body["success"] is False
        assert body["message"] == "Document not found"

    def test_get_requires_authentication(self, client, uploaded_document):
        doc_id = uploaded_document["document_id"]
        response = client.get(f"{DOCUMENTS_BASE}/{doc_id}")
        assert response.status_code == 401


# ── DELETE /v1/documents/{document_id} ────────────────────────────────────


class TestDeleteDocument:
    def test_delete_returns_200(self, client, api_key_headers, uploaded_document):
        doc_id = uploaded_document["document_id"]
        response = client.delete(f"{DOCUMENTS_BASE}/{doc_id}", headers=api_key_headers)
        assert response.status_code == 200

    def test_delete_response_envelope(self, client, api_key_headers, uploaded_document):
        doc_id = uploaded_document["document_id"]
        response = client.delete(f"{DOCUMENTS_BASE}/{doc_id}", headers=api_key_headers)
        body = response.json()

        assert body["success"] is True
        assert body["message"] == "Document removed successfully"
        assert body["data"]["document_id"] == doc_id

    def test_delete_removes_document(self, client, api_key_headers, uploaded_document):
        doc_id = uploaded_document["document_id"]
        client.delete(f"{DOCUMENTS_BASE}/{doc_id}", headers=api_key_headers)

        response = client.get(f"{DOCUMENTS_BASE}/{doc_id}", headers=api_key_headers)
        assert response.status_code == 404

    def test_delete_nonexistent_document(self, client, api_key_headers):
        response = client.delete(
            f"{DOCUMENTS_BASE}/doc_doesnotexist", headers=api_key_headers
        )
        assert response.status_code == 404

    def test_delete_from_complete_submission_rejected(
        self, client, api_key_headers, created_submission, uploaded_document
    ):
        sid = created_submission["submission_id"]
        doc_id = uploaded_document["document_id"]

        # Progress to complete
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

        response = client.delete(f"{DOCUMENTS_BASE}/{doc_id}", headers=api_key_headers)
        assert response.status_code == 422

        body = response.json()
        assert body["success"] is False
        assert "complete" in body["message"]

    def test_delete_requires_authentication(self, client, uploaded_document):
        doc_id = uploaded_document["document_id"]
        response = client.delete(f"{DOCUMENTS_BASE}/{doc_id}")
        assert response.status_code == 401
