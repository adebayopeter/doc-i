"""
Tests for the API keys admin router.

Covers:
- CRUD operations for API keys
- Admin-only access enforcement
- Process access control
- Key rotation
- Usage tracking (last_used_at, request_count)
- Backward compatibility with master SECRET_KEY
"""

from datetime import datetime, timedelta, timezone

from db.models import ApiKey, Process
from services.api_keys import generate_api_key


class TestCreateApiKey:
    """Tests for POST /v1/admin/keys."""

    def test_create_key_success(self, client, db_session, api_key_headers):
        """Should create a new API key and return the full key once."""
        response = client.post(
            "/v1/admin/keys",
            json={
                "name": "Test Key",
                "process_ids": [],
                "scopes": ["read", "write"],
            },
            headers=api_key_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert data["message"] == "API key created successfully"
        assert "key" in data["data"]  # Full key returned
        assert data["data"]["key"].startswith("doci_key_")
        assert data["data"]["name"] == "Test Key"
        assert data["data"]["is_admin"] is True  # Empty process_ids

    def test_create_key_with_process_scope(self, client, db_session, api_key_headers):
        """Should create a key scoped to specific processes."""
        # First create a process
        process = Process(name="Test Process")
        db_session.add(process)
        db_session.commit()

        response = client.post(
            "/v1/admin/keys",
            json={
                "name": "Scoped Key",
                "process_ids": [process.id],
                "scopes": ["read"],
            },
            headers=api_key_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["data"]["process_ids"] == [process.id]
        assert data["data"]["is_admin"] is False
        assert data["data"]["scopes"] == ["read"]

    def test_create_key_duplicate_name_rejected(
        self, client, db_session, api_key_headers
    ):
        """Should reject duplicate key names."""
        # Create first key
        client.post(
            "/v1/admin/keys",
            json={"name": "Duplicate Name", "process_ids": [], "scopes": ["read"]},
            headers=api_key_headers,
        )

        # Try to create second with same name
        response = client.post(
            "/v1/admin/keys",
            json={"name": "Duplicate Name", "process_ids": [], "scopes": ["write"]},
            headers=api_key_headers,
        )
        assert response.status_code == 409
        assert "already exists" in response.json()["message"]

    def test_create_key_invalid_process_id_rejected(
        self, client, db_session, api_key_headers
    ):
        """Should reject keys with non-existent process IDs."""
        response = client.post(
            "/v1/admin/keys",
            json={
                "name": "Invalid Process Key",
                "process_ids": ["proc_nonexistent"],
                "scopes": ["read"],
            },
            headers=api_key_headers,
        )
        assert response.status_code == 422
        assert "Invalid process_id" in response.json()["message"]

    def test_create_key_requires_admin(self, client, db_session, api_key_headers):
        """Non-admin keys should not be able to create keys."""
        # Create a non-admin key
        process = Process(name="Test Process")
        db_session.add(process)
        db_session.commit()

        full_key, key_hash, key_prefix = generate_api_key()
        non_admin_key = ApiKey(
            name="Non-Admin Key",
            key_prefix=key_prefix,
            key_hash=key_hash,
            process_ids=[process.id],  # Non-empty = not admin
            scopes=["read", "write"],
        )
        db_session.add(non_admin_key)
        db_session.commit()

        # Try to create a key with the non-admin key
        response = client.post(
            "/v1/admin/keys",
            json={"name": "New Key", "process_ids": [], "scopes": ["read"]},
            headers={"X-API-Key": full_key},
        )
        assert response.status_code == 403
        assert "admin access" in response.json()["message"]


class TestListApiKeys:
    """Tests for GET /v1/admin/keys."""

    def test_list_keys_empty(self, client, db_session, api_key_headers):
        """Should return empty list when no keys exist."""
        response = client.get("/v1/admin/keys", headers=api_key_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["items"] == []
        assert data["data"]["total"] == 0

    def test_list_keys_returns_all(self, client, db_session, api_key_headers):
        """Should return all keys."""
        # Create some keys
        for i in range(3):
            full_key, key_hash, key_prefix = generate_api_key()
            key = ApiKey(
                name=f"Key {i}",
                key_prefix=key_prefix,
                key_hash=key_hash,
                process_ids=[],
                scopes=["read"],
            )
            db_session.add(key)
        db_session.commit()

        response = client.get("/v1/admin/keys", headers=api_key_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["total"] == 3
        assert len(data["data"]["items"]) == 3

    def test_list_keys_never_exposes_hash(self, client, db_session, api_key_headers):
        """Listed keys should never include the hash or full key."""
        full_key, key_hash, key_prefix = generate_api_key()
        key = ApiKey(
            name="Secret Key",
            key_prefix=key_prefix,
            key_hash=key_hash,
            process_ids=[],
            scopes=["read"],
        )
        db_session.add(key)
        db_session.commit()

        response = client.get("/v1/admin/keys", headers=api_key_headers)
        data = response.json()
        item = data["data"]["items"][0]
        assert "key_hash" not in item
        assert "key" not in item
        assert "hash" not in str(item).lower() or "key_hash" not in item
        assert item["key_prefix"] == key_prefix


class TestGetApiKey:
    """Tests for GET /v1/admin/keys/{id}."""

    def test_get_key_success(self, client, db_session, api_key_headers):
        """Should return key details."""
        full_key, key_hash, key_prefix = generate_api_key()
        key = ApiKey(
            name="Test Key",
            key_prefix=key_prefix,
            key_hash=key_hash,
            process_ids=[],
            scopes=["read", "write"],
        )
        db_session.add(key)
        db_session.commit()

        response = client.get(f"/v1/admin/keys/{key.id}", headers=api_key_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["id"] == key.id
        assert data["data"]["name"] == "Test Key"
        assert data["data"]["key_prefix"] == key_prefix

    def test_get_key_not_found(self, client, db_session, api_key_headers):
        """Should return 404 for non-existent key."""
        response = client.get("/v1/admin/keys/key_nonexistent", headers=api_key_headers)
        assert response.status_code == 404


class TestUpdateApiKey:
    """Tests for PATCH /v1/admin/keys/{id}."""

    def test_update_key_name(self, client, db_session, api_key_headers):
        """Should update key name."""
        full_key, key_hash, key_prefix = generate_api_key()
        key = ApiKey(
            name="Original Name",
            key_prefix=key_prefix,
            key_hash=key_hash,
            process_ids=[],
            scopes=["read"],
        )
        db_session.add(key)
        db_session.commit()

        response = client.patch(
            f"/v1/admin/keys/{key.id}",
            json={"name": "Updated Name"},
            headers=api_key_headers,
        )
        assert response.status_code == 200
        assert response.json()["data"]["name"] == "Updated Name"

    def test_update_key_deactivate(self, client, db_session, api_key_headers):
        """Should deactivate a key."""
        full_key, key_hash, key_prefix = generate_api_key()
        key = ApiKey(
            name="Active Key",
            key_prefix=key_prefix,
            key_hash=key_hash,
            process_ids=[],
            scopes=["read"],
            is_active=True,
        )
        db_session.add(key)
        db_session.commit()

        response = client.patch(
            f"/v1/admin/keys/{key.id}",
            json={"is_active": False},
            headers=api_key_headers,
        )
        assert response.status_code == 200
        assert response.json()["data"]["is_active"] is False

    def test_update_key_process_ids(self, client, db_session, api_key_headers):
        """Should update process scope."""
        process = Process(name="New Process")
        db_session.add(process)
        db_session.commit()

        full_key, key_hash, key_prefix = generate_api_key()
        key = ApiKey(
            name="Scoped Key",
            key_prefix=key_prefix,
            key_hash=key_hash,
            process_ids=[],
            scopes=["read"],
        )
        db_session.add(key)
        db_session.commit()

        response = client.patch(
            f"/v1/admin/keys/{key.id}",
            json={"process_ids": [process.id]},
            headers=api_key_headers,
        )
        assert response.status_code == 200
        assert response.json()["data"]["process_ids"] == [process.id]
        assert response.json()["data"]["is_admin"] is False


class TestRotateApiKey:
    """Tests for POST /v1/admin/keys/{id}/rotate."""

    def test_rotate_key_success(self, client, db_session, api_key_headers):
        """Should generate new key and invalidate old one."""
        full_key, key_hash, key_prefix = generate_api_key()
        key = ApiKey(
            name="Rotating Key",
            key_prefix=key_prefix,
            key_hash=key_hash,
            process_ids=[],
            scopes=["read"],
        )
        db_session.add(key)
        db_session.commit()
        old_prefix = key.key_prefix

        response = client.post(
            f"/v1/admin/keys/{key.id}/rotate",
            headers=api_key_headers,
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["old_key_prefix"] == old_prefix
        assert data["new_key_prefix"] != old_prefix
        assert "new_key" in data
        assert data["new_key"].startswith("doci_key_")

    def test_old_key_invalid_after_rotate(self, client, db_session, api_key_headers):
        """Old key should not work after rotation."""
        full_key, key_hash, key_prefix = generate_api_key()
        key = ApiKey(
            name="Admin Rotating",
            key_prefix=key_prefix,
            key_hash=key_hash,
            process_ids=[],  # Admin key
            scopes=["read", "write"],
        )
        db_session.add(key)
        db_session.commit()

        # Rotate the key
        response = client.post(
            f"/v1/admin/keys/{key.id}/rotate",
            headers=api_key_headers,
        )
        new_key = response.json()["data"]["new_key"]

        # Old key should fail
        response = client.get("/v1/admin/keys", headers={"X-API-Key": full_key})
        assert response.status_code == 401

        # New key should work
        response = client.get("/v1/admin/keys", headers={"X-API-Key": new_key})
        assert response.status_code == 200


class TestDeleteApiKey:
    """Tests for DELETE /v1/admin/keys/{id}."""

    def test_delete_key_success(self, client, db_session, api_key_headers):
        """Should permanently delete a key."""
        full_key, key_hash, key_prefix = generate_api_key()
        key = ApiKey(
            name="Deletable Key",
            key_prefix=key_prefix,
            key_hash=key_hash,
            process_ids=[],
            scopes=["read"],
        )
        db_session.add(key)
        db_session.commit()
        key_id = key.id

        response = client.delete(f"/v1/admin/keys/{key_id}", headers=api_key_headers)
        assert response.status_code == 200
        assert response.json()["data"]["id"] == key_id

        # Verify it's gone
        response = client.get(f"/v1/admin/keys/{key_id}", headers=api_key_headers)
        assert response.status_code == 404


class TestAuthWithApiKeys:
    """Tests for authentication with database API keys."""

    def test_valid_key_accepted(self, client, db_session):
        """Valid API key should be accepted."""
        full_key, key_hash, key_prefix = generate_api_key()
        key = ApiKey(
            name="Valid Key",
            key_prefix=key_prefix,
            key_hash=key_hash,
            process_ids=[],
            scopes=["read", "write"],
        )
        db_session.add(key)
        db_session.commit()

        response = client.get("/v1/admin/keys", headers={"X-API-Key": full_key})
        assert response.status_code == 200

    def test_invalid_key_rejected(self, client, db_session):
        """Invalid API key should return 401."""
        response = client.get(
            "/v1/admin/keys", headers={"X-API-Key": "doci_key_invalid_key_12345678"}
        )
        assert response.status_code == 401
        assert "Invalid API key" in response.json()["message"]

    def test_disabled_key_rejected(self, client, db_session):
        """Disabled API key should return 401."""
        full_key, key_hash, key_prefix = generate_api_key()
        key = ApiKey(
            name="Disabled Key",
            key_prefix=key_prefix,
            key_hash=key_hash,
            process_ids=[],
            scopes=["read", "write"],
            is_active=False,
        )
        db_session.add(key)
        db_session.commit()

        response = client.get("/v1/admin/keys", headers={"X-API-Key": full_key})
        assert response.status_code == 401
        assert "disabled" in response.json()["message"]

    def test_expired_key_rejected(self, client, db_session):
        """Expired API key should return 401."""
        full_key, key_hash, key_prefix = generate_api_key()
        key = ApiKey(
            name="Expired Key",
            key_prefix=key_prefix,
            key_hash=key_hash,
            process_ids=[],
            scopes=["read", "write"],
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
        db_session.add(key)
        db_session.commit()

        response = client.get("/v1/admin/keys", headers={"X-API-Key": full_key})
        assert response.status_code == 401
        assert "expired" in response.json()["message"]

    def test_master_secret_key_still_works(self, client, db_session, api_key_headers):
        """Master SECRET_KEY from .env should still work as admin."""
        response = client.get("/v1/admin/keys", headers=api_key_headers)
        assert response.status_code == 200


class TestUsageTracking:
    """Tests for last_used_at and request_count updates."""

    def test_last_used_at_updated(self, client, db_session):
        """last_used_at should be updated on each request."""
        full_key, key_hash, key_prefix = generate_api_key()
        key = ApiKey(
            name="Tracking Key",
            key_prefix=key_prefix,
            key_hash=key_hash,
            process_ids=[],
            scopes=["read", "write"],
            last_used_at=None,
        )
        db_session.add(key)
        db_session.commit()

        # Make a request
        client.get("/v1/admin/keys", headers={"X-API-Key": full_key})

        # Check last_used_at was updated
        db_session.refresh(key)
        assert key.last_used_at is not None

    def test_request_count_incremented(self, client, db_session):
        """request_count should increment on each request."""
        full_key, key_hash, key_prefix = generate_api_key()
        key = ApiKey(
            name="Counter Key",
            key_prefix=key_prefix,
            key_hash=key_hash,
            process_ids=[],
            scopes=["read", "write"],
            request_count=0,
        )
        db_session.add(key)
        db_session.commit()

        # Make 3 requests
        for _ in range(3):
            client.get("/v1/admin/keys", headers={"X-API-Key": full_key})

        # Check count
        db_session.refresh(key)
        assert key.request_count == 3


class TestProcessAccessControl:
    """Tests for process-level access control."""

    def test_scoped_key_can_access_allowed_process(self, client, db_session):
        """Key scoped to process A should access process A."""
        process = Process(name="Allowed Process")
        db_session.add(process)
        db_session.commit()

        full_key, key_hash, key_prefix = generate_api_key()
        key = ApiKey(
            name="Scoped Key",
            key_prefix=key_prefix,
            key_hash=key_hash,
            process_ids=[process.id],
            scopes=["read", "write"],
        )
        db_session.add(key)
        db_session.commit()

        response = client.get(
            f"/v1/processes/{process.id}", headers={"X-API-Key": full_key}
        )
        assert response.status_code == 200

    def test_scoped_key_denied_other_process(self, client, db_session):
        """Key scoped to process A should NOT access process B."""
        process_a = Process(name="Process A")
        process_b = Process(name="Process B")
        db_session.add_all([process_a, process_b])
        db_session.commit()

        full_key, key_hash, key_prefix = generate_api_key()
        key = ApiKey(
            name="Scoped to A",
            key_prefix=key_prefix,
            key_hash=key_hash,
            process_ids=[process_a.id],
            scopes=["read", "write"],
        )
        db_session.add(key)
        db_session.commit()

        response = client.get(
            f"/v1/processes/{process_b.id}", headers={"X-API-Key": full_key}
        )
        assert response.status_code == 403
        assert "does not have access" in response.json()["message"]

    def test_admin_key_can_access_all_processes(self, client, db_session):
        """Admin key (empty process_ids) should access any process."""
        process = Process(name="Any Process")
        db_session.add(process)
        db_session.commit()

        full_key, key_hash, key_prefix = generate_api_key()
        key = ApiKey(
            name="Admin Key",
            key_prefix=key_prefix,
            key_hash=key_hash,
            process_ids=[],  # Admin
            scopes=["read", "write"],
        )
        db_session.add(key)
        db_session.commit()

        response = client.get(
            f"/v1/processes/{process.id}", headers={"X-API-Key": full_key}
        )
        assert response.status_code == 200

    def test_list_processes_filtered_for_scoped_key(self, client, db_session):
        """GET /v1/processes should only show accessible processes."""
        process_a = Process(name="Process A")
        process_b = Process(name="Process B")
        db_session.add_all([process_a, process_b])
        db_session.commit()

        full_key, key_hash, key_prefix = generate_api_key()
        key = ApiKey(
            name="Scoped to A",
            key_prefix=key_prefix,
            key_hash=key_hash,
            process_ids=[process_a.id],
            scopes=["read"],
        )
        db_session.add(key)
        db_session.commit()

        response = client.get("/v1/processes", headers={"X-API-Key": full_key})
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["process_id"] == process_a.id


class TestNonAdminKeyOnAdminEndpoints:
    """Tests that non-admin keys can't access admin endpoints."""

    def test_non_admin_denied_list_keys(self, client, db_session):
        """Non-admin key should get 403 on admin endpoints."""
        process = Process(name="Process")
        db_session.add(process)
        db_session.commit()

        full_key, key_hash, key_prefix = generate_api_key()
        key = ApiKey(
            name="Non-Admin",
            key_prefix=key_prefix,
            key_hash=key_hash,
            process_ids=[process.id],  # Not admin
            scopes=["read", "write"],
        )
        db_session.add(key)
        db_session.commit()

        response = client.get("/v1/admin/keys", headers={"X-API-Key": full_key})
        assert response.status_code == 403
        assert "admin access" in response.json()["message"]

    def test_non_admin_denied_config_endpoints(self, client, db_session):
        """Non-admin key should get 403 on config endpoints."""
        process = Process(name="Process")
        db_session.add(process)
        db_session.commit()

        full_key, key_hash, key_prefix = generate_api_key()
        key = ApiKey(
            name="Non-Admin",
            key_prefix=key_prefix,
            key_hash=key_hash,
            process_ids=[process.id],
            scopes=["read", "write"],
        )
        db_session.add(key)
        db_session.commit()

        response = client.get("/v1/config/rules", headers={"X-API-Key": full_key})
        assert response.status_code == 403
