"""
Tests for the /health endpoint.
"""


def test_health_returns_200(client):
    response = client.get("/health")
    assert response.status_code == 200


def test_health_response_envelope(client):
    """Response must follow the standard envelope format."""
    response = client.get("/health")
    body = response.json()

    assert body["success"] is True
    assert body["message"] == "API is running"
    assert body["data"] is not None


def test_health_data_fields(client):
    """Response data must contain status, version and environment."""
    response = client.get("/health")
    data = response.json()["data"]

    assert data["status"] == "ok"
    assert data["version"] == "1.0.0"
    assert data["environment"] == "development"


def test_health_no_auth_required(client):
    """Health endpoint must be accessible without an API key."""
    response = client.get("/health")
    assert response.status_code == 200
