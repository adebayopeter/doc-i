"""
Tests for /v1/config endpoints.
"""

import pytest

CONFIG_BASE = "/v1/config"


# ── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture
def seeded_rules(db_session):
    """Insert a set of validation rules directly into the test DB."""
    from db.models import ValidationRule

    rules = [
        ValidationRule(
            id="rule_test_r01",
            name="Full name required",
            rule_type="required",
            field="Full Name",
            severity="error",
            is_enabled=True,
        ),
        ValidationRule(
            id="rule_test_r02",
            name="NIN format (11 digits)",
            rule_type="format",
            field="NIN",
            pattern=r"^\d{11}$",
            severity="error",
            is_enabled=True,
        ),
        ValidationRule(
            id="rule_test_r03",
            name="Applicant aged 18 or over",
            rule_type="logical",
            field="Date of Birth",
            check="min_age_18",
            severity="error",
            is_enabled=True,
        ),
        ValidationRule(
            id="rule_test_r04",
            name="Disabled rule",
            rule_type="required",
            field="Address",
            severity="warning",
            is_enabled=False,
        ),
    ]
    for rule in rules:
        db_session.add(rule)
    db_session.commit()
    return rules


# ── GET /v1/config/rules ──────────────────────────────────────────────────


class TestListRules:
    def test_list_returns_200(self, client, api_key_headers):
        response = client.get(f"{CONFIG_BASE}/rules", headers=api_key_headers)
        assert response.status_code == 200

    def test_list_response_envelope(self, client, api_key_headers):
        response = client.get(f"{CONFIG_BASE}/rules", headers=api_key_headers)
        body = response.json()

        assert body["success"] is True
        assert body["message"] == "Validation rules retrieved successfully"
        assert body["data"] is not None

    def test_list_returns_items_and_totals(self, client, api_key_headers):
        response = client.get(f"{CONFIG_BASE}/rules", headers=api_key_headers)
        data = response.json()["data"]

        assert "items" in data
        assert "total" in data
        assert "enabled" in data
        assert "disabled" in data

    def test_list_total_matches_items(self, client, api_key_headers, seeded_rules):
        response = client.get(f"{CONFIG_BASE}/rules", headers=api_key_headers)
        data = response.json()["data"]

        assert data["total"] == len(data["items"])

    def test_list_enabled_disabled_counts(self, client, api_key_headers, seeded_rules):
        response = client.get(f"{CONFIG_BASE}/rules", headers=api_key_headers)
        data = response.json()["data"]

        assert data["enabled"] + data["disabled"] == data["total"]

    def test_list_includes_seeded_rules(self, client, api_key_headers, seeded_rules):
        response = client.get(f"{CONFIG_BASE}/rules", headers=api_key_headers)
        data = response.json()["data"]

        rule_ids = [r["id"] for r in data["items"]]
        assert "rule_test_r01" in rule_ids
        assert "rule_test_r02" in rule_ids

    def test_list_rule_has_required_fields(self, client, api_key_headers, seeded_rules):
        response = client.get(f"{CONFIG_BASE}/rules", headers=api_key_headers)
        items = response.json()["data"]["items"]

        if items:
            rule = items[0]
            assert "id" in rule
            assert "name" in rule
            assert "rule_type" in rule
            assert "field" in rule
            assert "severity" in rule
            assert "is_enabled" in rule

    def test_list_requires_authentication(self, client):
        response = client.get(f"{CONFIG_BASE}/rules")
        assert response.status_code == 401


# ── GET /v1/config/rules/{rule_id} ────────────────────────────────────────


class TestGetRule:
    def test_get_returns_200(self, client, api_key_headers, seeded_rules):
        response = client.get(
            f"{CONFIG_BASE}/rules/rule_test_r01",
            headers=api_key_headers,
        )
        assert response.status_code == 200

    def test_get_response_envelope(self, client, api_key_headers, seeded_rules):
        response = client.get(
            f"{CONFIG_BASE}/rules/rule_test_r01",
            headers=api_key_headers,
        )
        body = response.json()

        assert body["success"] is True
        assert body["message"] == "Validation rule retrieved successfully"

    def test_get_returns_correct_rule(self, client, api_key_headers, seeded_rules):
        response = client.get(
            f"{CONFIG_BASE}/rules/rule_test_r01",
            headers=api_key_headers,
        )
        data = response.json()["data"]

        assert data["id"] == "rule_test_r01"
        assert data["name"] == "Full name required"
        assert data["rule_type"] == "required"
        assert data["field"] == "Full Name"

    def test_get_nonexistent_rule(self, client, api_key_headers):
        response = client.get(
            f"{CONFIG_BASE}/rules/rule_doesnotexist",
            headers=api_key_headers,
        )
        assert response.status_code == 404

        body = response.json()
        assert body["success"] is False
        assert "not found" in body["message"].lower()

    def test_get_requires_authentication(self, client, seeded_rules):
        response = client.get(f"{CONFIG_BASE}/rules/rule_test_r01")
        assert response.status_code == 401


# ── PATCH /v1/config/rules/{rule_id} ─────────────────────────────────────


class TestUpdateRule:
    def test_update_returns_200(self, client, api_key_headers, seeded_rules):
        response = client.patch(
            f"{CONFIG_BASE}/rules/rule_test_r01",
            json={"enabled": False},
            headers=api_key_headers,
        )
        assert response.status_code == 200

    def test_update_response_envelope(self, client, api_key_headers, seeded_rules):
        response = client.patch(
            f"{CONFIG_BASE}/rules/rule_test_r01",
            json={"enabled": False},
            headers=api_key_headers,
        )
        body = response.json()

        assert body["success"] is True
        assert body["message"] == "Validation rule updated successfully"

    def test_disable_rule(self, client, api_key_headers, seeded_rules):
        response = client.patch(
            f"{CONFIG_BASE}/rules/rule_test_r01",
            json={"enabled": False},
            headers=api_key_headers,
        )
        assert response.json()["data"]["is_enabled"] is False

    def test_enable_disabled_rule(self, client, api_key_headers, seeded_rules):
        response = client.patch(
            f"{CONFIG_BASE}/rules/rule_test_r04",
            json={"enabled": True},
            headers=api_key_headers,
        )
        assert response.json()["data"]["is_enabled"] is True

    def test_change_severity_to_warning(self, client, api_key_headers, seeded_rules):
        response = client.patch(
            f"{CONFIG_BASE}/rules/rule_test_r01",
            json={"severity": "warning"},
            headers=api_key_headers,
        )
        assert response.json()["data"]["severity"] == "warning"

    def test_change_severity_to_error(self, client, api_key_headers, seeded_rules):
        client.patch(
            f"{CONFIG_BASE}/rules/rule_test_r01",
            json={"severity": "warning"},
            headers=api_key_headers,
        )
        response = client.patch(
            f"{CONFIG_BASE}/rules/rule_test_r01",
            json={"severity": "error"},
            headers=api_key_headers,
        )
        assert response.json()["data"]["severity"] == "error"

    def test_update_both_fields_at_once(self, client, api_key_headers, seeded_rules):
        response = client.patch(
            f"{CONFIG_BASE}/rules/rule_test_r01",
            json={"enabled": False, "severity": "warning"},
            headers=api_key_headers,
        )
        data = response.json()["data"]

        assert data["is_enabled"] is False
        assert data["severity"] == "warning"

    def test_update_persists(self, client, api_key_headers, seeded_rules):
        client.patch(
            f"{CONFIG_BASE}/rules/rule_test_r01",
            json={"enabled": False},
            headers=api_key_headers,
        )
        response = client.get(
            f"{CONFIG_BASE}/rules/rule_test_r01",
            headers=api_key_headers,
        )
        assert response.json()["data"]["is_enabled"] is False

    def test_invalid_severity_returns_422(self, client, api_key_headers, seeded_rules):
        response = client.patch(
            f"{CONFIG_BASE}/rules/rule_test_r01",
            json={"severity": "critical"},
            headers=api_key_headers,
        )
        assert response.status_code == 422

        body = response.json()
        assert body["success"] is False
        assert "critical" in body["message"]

    def test_update_nonexistent_rule(self, client, api_key_headers):
        response = client.patch(
            f"{CONFIG_BASE}/rules/rule_doesnotexist",
            json={"enabled": False},
            headers=api_key_headers,
        )
        assert response.status_code == 404

    def test_update_requires_authentication(self, client, seeded_rules):
        response = client.patch(
            f"{CONFIG_BASE}/rules/rule_test_r01",
            json={"enabled": False},
        )
        assert response.status_code == 401


# ── GET /v1/config/thresholds ─────────────────────────────────────────────


class TestGetThresholds:
    def test_get_returns_200(self, client, api_key_headers):
        response = client.get(f"{CONFIG_BASE}/thresholds", headers=api_key_headers)
        assert response.status_code == 200

    def test_get_response_envelope(self, client, api_key_headers):
        response = client.get(f"{CONFIG_BASE}/thresholds", headers=api_key_headers)
        body = response.json()

        assert body["success"] is True
        assert body["message"] == "Thresholds retrieved successfully"

    def test_get_returns_threshold_values(self, client, api_key_headers):
        response = client.get(f"{CONFIG_BASE}/thresholds", headers=api_key_headers)
        data = response.json()["data"]

        assert "auto_above" in data
        assert "manual_below" in data
        assert "description" in data

    def test_get_default_thresholds(self, client, api_key_headers):
        response = client.get(f"{CONFIG_BASE}/thresholds", headers=api_key_headers)
        data = response.json()["data"]

        assert data["auto_above"] == 85
        assert data["manual_below"] == 60

    def test_get_requires_authentication(self, client):
        response = client.get(f"{CONFIG_BASE}/thresholds")
        assert response.status_code == 401


# ── PUT /v1/config/thresholds ─────────────────────────────────────────────


class TestUpdateThresholds:
    def test_update_returns_200(self, client, api_key_headers):
        response = client.put(
            f"{CONFIG_BASE}/thresholds",
            json={"auto_above": 90, "manual_below": 65},
            headers=api_key_headers,
        )
        assert response.status_code == 200

    def test_update_response_envelope(self, client, api_key_headers):
        response = client.put(
            f"{CONFIG_BASE}/thresholds",
            json={"auto_above": 90, "manual_below": 65},
            headers=api_key_headers,
        )
        body = response.json()

        assert body["success"] is True
        assert body["message"] == "Thresholds updated successfully"

    def test_update_returns_new_values(self, client, api_key_headers):
        response = client.put(
            f"{CONFIG_BASE}/thresholds",
            json={"auto_above": 90, "manual_below": 65},
            headers=api_key_headers,
        )
        data = response.json()["data"]

        assert data["auto_above"] == 90
        assert data["manual_below"] == 65

    def test_update_returns_previous_values(self, client, api_key_headers):
        response = client.put(
            f"{CONFIG_BASE}/thresholds",
            json={"auto_above": 90, "manual_below": 65},
            headers=api_key_headers,
        )
        data = response.json()["data"]

        assert "previous" in data
        assert "auto_above" in data["previous"]
        assert "manual_below" in data["previous"]

    def test_update_returns_description(self, client, api_key_headers):
        response = client.put(
            f"{CONFIG_BASE}/thresholds",
            json={"auto_above": 90, "manual_below": 65},
            headers=api_key_headers,
        )
        data = response.json()["data"]

        assert "description" in data
        assert "90%" in data["description"]["auto"]
        assert "65%" in data["description"]["manual"]

    def test_auto_above_must_be_greater_than_manual_below(
        self, client, api_key_headers
    ):
        response = client.put(
            f"{CONFIG_BASE}/thresholds",
            json={"auto_above": 60, "manual_below": 60},
            headers=api_key_headers,
        )
        assert response.status_code == 422

        body = response.json()
        assert body["success"] is False
        assert "greater than" in body["message"]

    def test_auto_above_below_manual_below_rejected(self, client, api_key_headers):
        response = client.put(
            f"{CONFIG_BASE}/thresholds",
            json={"auto_above": 50, "manual_below": 70},
            headers=api_key_headers,
        )
        assert response.status_code == 422

    def test_auto_above_minimum_validated(self, client, api_key_headers):
        """auto_above must be at least 51."""
        response = client.put(
            f"{CONFIG_BASE}/thresholds",
            json={"auto_above": 40, "manual_below": 20},
            headers=api_key_headers,
        )
        assert response.status_code == 422

    def test_manual_below_maximum_validated(self, client, api_key_headers):
        """manual_below must be at most 79."""
        response = client.put(
            f"{CONFIG_BASE}/thresholds",
            json={"auto_above": 95, "manual_below": 85},
            headers=api_key_headers,
        )
        assert response.status_code == 422

    def test_update_requires_authentication(self, client):
        response = client.put(
            f"{CONFIG_BASE}/thresholds",
            json={"auto_above": 90, "manual_below": 65},
        )
        assert response.status_code == 401
