"""
Tests for the document categories router.

POST   /v1/config/categories
GET    /v1/config/categories
GET    /v1/config/categories/{id}
PATCH  /v1/config/categories/{id}
DELETE /v1/config/categories/{id}
"""

import pytest

CATEGORIES_BASE = "/v1/config/categories"


@pytest.fixture
def created_category(client, api_key_headers):
    """Creates a single category and returns its data."""
    response = client.post(
        CATEGORIES_BASE,
        json={"name": "Identity", "description": "Government-issued ID documents"},
        headers=api_key_headers,
    )
    assert response.status_code == 201
    return response.json()["data"]


@pytest.fixture
def multiple_categories(client, api_key_headers):
    """Creates several categories for list/filter tests."""
    names = [
        ("Financial", "Bank statements and financial records"),
        ("Income", "Employment and salary documents"),
        ("Supporting", "Optional supporting documents"),
    ]
    created = []
    for name, desc in names:
        response = client.post(
            CATEGORIES_BASE,
            json={"name": name, "description": desc},
            headers=api_key_headers,
        )
        assert response.status_code == 201
        created.append(response.json()["data"])
    return created


# ── POST /v1/config/categories ─────────────────────────────────────────────


class TestCreateCategory:
    def test_create_returns_201(self, client, api_key_headers):
        response = client.post(
            CATEGORIES_BASE,
            json={"name": "Identity"},
            headers=api_key_headers,
        )
        assert response.status_code == 201

    def test_create_response_envelope(self, client, api_key_headers):
        response = client.post(
            CATEGORIES_BASE,
            json={"name": "Financial"},
            headers=api_key_headers,
        )
        body = response.json()
        assert body["success"] is True
        assert body["message"] == "Category created successfully"
        assert body["data"] is not None

    def test_create_returns_category_id(self, client, api_key_headers):
        response = client.post(
            CATEGORIES_BASE,
            json={"name": "Income"},
            headers=api_key_headers,
        )
        data = response.json()["data"]
        assert data["id"].startswith("cat_")

    def test_create_stores_name_and_description(self, client, api_key_headers):
        response = client.post(
            CATEGORIES_BASE,
            json={
                "name": "Legal",
                "description": "Legal and compliance documents",
            },
            headers=api_key_headers,
        )
        data = response.json()["data"]
        assert data["name"] == "Legal"
        assert data["description"] == "Legal and compliance documents"

    def test_create_without_description(self, client, api_key_headers):
        response = client.post(
            CATEGORIES_BASE,
            json={"name": "Supporting"},
            headers=api_key_headers,
        )
        assert response.status_code == 201
        assert response.json()["data"]["description"] is None

    def test_create_is_active_by_default(self, client, api_key_headers):
        response = client.post(
            CATEGORIES_BASE,
            json={"name": "Property"},
            headers=api_key_headers,
        )
        assert response.json()["data"]["is_active"] is True

    def test_create_rejects_duplicate_name(
        self, client, api_key_headers, created_category
    ):
        response = client.post(
            CATEGORIES_BASE,
            json={"name": "Identity"},
            headers=api_key_headers,
        )
        assert response.status_code == 422
        assert "already exists" in response.json()["message"]

    def test_create_duplicate_case_insensitive(
        self, client, api_key_headers, created_category
    ):
        response = client.post(
            CATEGORIES_BASE,
            json={"name": "identity"},
            headers=api_key_headers,
        )
        assert response.status_code == 422

    def test_create_requires_name(self, client, api_key_headers):
        response = client.post(
            CATEGORIES_BASE,
            json={"description": "No name provided"},
            headers=api_key_headers,
        )
        assert response.status_code == 422

    def test_create_name_minimum_length(self, client, api_key_headers):
        response = client.post(
            CATEGORIES_BASE,
            json={"name": "A"},
            headers=api_key_headers,
        )
        assert response.status_code == 422

    def test_create_reactivates_soft_deleted_category(
        self, client, api_key_headers, created_category
    ):
        cat_id = created_category["id"]
        client.delete(f"{CATEGORIES_BASE}/{cat_id}", headers=api_key_headers)

        response = client.post(
            CATEGORIES_BASE,
            json={"name": "Identity"},
            headers=api_key_headers,
        )
        assert response.status_code == 201
        assert response.json()["data"]["is_active"] is True
        assert response.json()["message"] == "Category reactivated successfully"

    def test_create_requires_authentication(self, client):
        response = client.post(
            CATEGORIES_BASE,
            json={"name": "Identity"},
        )
        assert response.status_code == 401


# ── GET /v1/config/categories ──────────────────────────────────────────────


class TestListCategories:
    def test_list_returns_200(self, client, api_key_headers):
        response = client.get(CATEGORIES_BASE, headers=api_key_headers)
        assert response.status_code == 200

    def test_list_response_envelope(self, client, api_key_headers):
        response = client.get(CATEGORIES_BASE, headers=api_key_headers)
        body = response.json()
        assert body["success"] is True
        assert body["message"] == "Categories retrieved successfully"

    def test_list_returns_items_and_totals(self, client, api_key_headers):
        response = client.get(CATEGORIES_BASE, headers=api_key_headers)
        data = response.json()["data"]
        assert "items" in data
        assert "total" in data
        assert "active" in data

    def test_list_includes_created_category(
        self, client, api_key_headers, created_category
    ):
        response = client.get(CATEGORIES_BASE, headers=api_key_headers)
        ids = [c["id"] for c in response.json()["data"]["items"]]
        assert created_category["id"] in ids

    def test_list_is_alphabetical(self, client, api_key_headers, multiple_categories):
        response = client.get(CATEGORIES_BASE, headers=api_key_headers)
        names = [c["name"] for c in response.json()["data"]["items"]]
        assert names == sorted(names)

    def test_list_excludes_inactive_by_default(
        self, client, api_key_headers, created_category
    ):
        cat_id = created_category["id"]
        client.delete(f"{CATEGORIES_BASE}/{cat_id}", headers=api_key_headers)

        response = client.get(CATEGORIES_BASE, headers=api_key_headers)
        ids = [c["id"] for c in response.json()["data"]["items"]]
        assert cat_id not in ids

    def test_list_includes_inactive_when_requested(
        self, client, api_key_headers, created_category
    ):
        cat_id = created_category["id"]
        client.delete(f"{CATEGORIES_BASE}/{cat_id}", headers=api_key_headers)

        response = client.get(
            f"{CATEGORIES_BASE}?include_inactive=true",
            headers=api_key_headers,
        )
        ids = [c["id"] for c in response.json()["data"]["items"]]
        assert cat_id in ids

    def test_list_requires_authentication(self, client):
        response = client.get(CATEGORIES_BASE)
        assert response.status_code == 401


# ── GET /v1/config/categories/{id} ────────────────────────────────────────


class TestGetCategory:
    def test_get_returns_200(self, client, api_key_headers, created_category):
        response = client.get(
            f"{CATEGORIES_BASE}/{created_category['id']}",
            headers=api_key_headers,
        )
        assert response.status_code == 200

    def test_get_response_envelope(self, client, api_key_headers, created_category):
        response = client.get(
            f"{CATEGORIES_BASE}/{created_category['id']}",
            headers=api_key_headers,
        )
        body = response.json()
        assert body["success"] is True
        assert body["message"] == "Category retrieved successfully"

    def test_get_returns_correct_category(
        self, client, api_key_headers, created_category
    ):
        response = client.get(
            f"{CATEGORIES_BASE}/{created_category['id']}",
            headers=api_key_headers,
        )
        data = response.json()["data"]
        assert data["id"] == created_category["id"]
        assert data["name"] == "Identity"

    def test_get_nonexistent_category(self, client, api_key_headers):
        response = client.get(
            f"{CATEGORIES_BASE}/cat_doesnotexist",
            headers=api_key_headers,
        )
        assert response.status_code == 404

    def test_get_requires_authentication(self, client, created_category):
        response = client.get(f"{CATEGORIES_BASE}/{created_category['id']}")
        assert response.status_code == 401


# ── PATCH /v1/config/categories/{id} ──────────────────────────────────────


class TestUpdateCategory:
    def test_update_returns_200(self, client, api_key_headers, created_category):
        response = client.patch(
            f"{CATEGORIES_BASE}/{created_category['id']}",
            json={"name": "Identity Documents"},
            headers=api_key_headers,
        )
        assert response.status_code == 200

    def test_update_response_envelope(self, client, api_key_headers, created_category):
        response = client.patch(
            f"{CATEGORIES_BASE}/{created_category['id']}",
            json={"description": "Updated description"},
            headers=api_key_headers,
        )
        body = response.json()
        assert body["success"] is True
        assert body["message"] == "Category updated successfully"

    def test_update_name(self, client, api_key_headers, created_category):
        response = client.patch(
            f"{CATEGORIES_BASE}/{created_category['id']}",
            json={"name": "ID Documents"},
            headers=api_key_headers,
        )
        assert response.json()["data"]["name"] == "ID Documents"

    def test_update_description(self, client, api_key_headers, created_category):
        response = client.patch(
            f"{CATEGORIES_BASE}/{created_category['id']}",
            json={"description": "New description"},
            headers=api_key_headers,
        )
        assert response.json()["data"]["description"] == "New description"

    def test_update_both_fields(self, client, api_key_headers, created_category):
        response = client.patch(
            f"{CATEGORIES_BASE}/{created_category['id']}",
            json={"name": "KYC Documents", "description": "Know your customer"},
            headers=api_key_headers,
        )
        data = response.json()["data"]
        assert data["name"] == "KYC Documents"
        assert data["description"] == "Know your customer"

    def test_update_persists(self, client, api_key_headers, created_category):
        client.patch(
            f"{CATEGORIES_BASE}/{created_category['id']}",
            json={"name": "Updated Identity"},
            headers=api_key_headers,
        )
        response = client.get(
            f"{CATEGORIES_BASE}/{created_category['id']}",
            headers=api_key_headers,
        )
        assert response.json()["data"]["name"] == "Updated Identity"

    def test_update_rejects_duplicate_name(
        self, client, api_key_headers, created_category, multiple_categories
    ):
        response = client.patch(
            f"{CATEGORIES_BASE}/{created_category['id']}",
            json={"name": "Financial"},
            headers=api_key_headers,
        )
        assert response.status_code == 422
        assert "already taken" in response.json()["message"]

    def test_update_same_name_is_allowed(
        self, client, api_key_headers, created_category
    ):
        """Patching with the same name should succeed — not a duplicate."""
        response = client.patch(
            f"{CATEGORIES_BASE}/{created_category['id']}",
            json={"name": "Identity"},
            headers=api_key_headers,
        )
        assert response.status_code == 200

    def test_update_nonexistent_category(self, client, api_key_headers):
        response = client.patch(
            f"{CATEGORIES_BASE}/cat_doesnotexist",
            json={"name": "Whatever"},
            headers=api_key_headers,
        )
        assert response.status_code == 404

    def test_update_requires_authentication(self, client, created_category):
        response = client.patch(
            f"{CATEGORIES_BASE}/{created_category['id']}",
            json={"name": "No auth"},
        )
        assert response.status_code == 401


# ── DELETE /v1/config/categories/{id} ─────────────────────────────────────


class TestDeleteCategory:
    def test_delete_returns_200(self, client, api_key_headers, created_category):
        response = client.delete(
            f"{CATEGORIES_BASE}/{created_category['id']}",
            headers=api_key_headers,
        )
        assert response.status_code == 200

    def test_delete_response_envelope(self, client, api_key_headers, created_category):
        response = client.delete(
            f"{CATEGORIES_BASE}/{created_category['id']}",
            headers=api_key_headers,
        )
        body = response.json()
        assert body["success"] is True
        assert body["message"] == "Category deactivated successfully"

    def test_delete_is_soft_delete(self, client, api_key_headers, created_category):
        cat_id = created_category["id"]
        client.delete(f"{CATEGORIES_BASE}/{cat_id}", headers=api_key_headers)

        response = client.get(
            f"{CATEGORIES_BASE}?include_inactive=true",
            headers=api_key_headers,
        )
        ids = [c["id"] for c in response.json()["data"]["items"]]
        assert cat_id in ids

    def test_delete_removes_from_active_list(
        self, client, api_key_headers, created_category
    ):
        cat_id = created_category["id"]
        client.delete(f"{CATEGORIES_BASE}/{cat_id}", headers=api_key_headers)

        response = client.get(CATEGORIES_BASE, headers=api_key_headers)
        ids = [c["id"] for c in response.json()["data"]["items"]]
        assert cat_id not in ids

    def test_delete_nonexistent_category(self, client, api_key_headers):
        response = client.delete(
            f"{CATEGORIES_BASE}/cat_doesnotexist",
            headers=api_key_headers,
        )
        assert response.status_code == 404

    def test_delete_requires_authentication(self, client, created_category):
        response = client.delete(f"{CATEGORIES_BASE}/{created_category['id']}")
        assert response.status_code == 401
