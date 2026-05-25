"""
Tests for the validation rule engine.
"""

from services.validation import run_rules


class FakeRule:
    """Minimal fake ValidationRule ORM object."""

    def __init__(
        self,
        rule_id,
        name,
        rule_type,
        field,
        severity="error",
        enabled=True,
        check=None,
        pattern=None,
    ):
        self.id = rule_id
        self.name = name
        self.rule_type = rule_type
        self.field = field
        self.severity = severity
        self.is_enabled = enabled
        self.check = check
        self.pattern = pattern


def _record(field, value, confidence=90, conflict=False, null=False):
    return {
        field: {
            "bestValue": value,
            "bestConfidence": confidence,
            "hasConflict": conflict,
            "isNull": null,
            "allValues": [{"value": value}],
        }
    }


class TestRequiredRules:
    def test_required_field_present_passes(self):
        rule = FakeRule("r1", "Full name required", "required", "Full Name")
        record = _record("Full Name", "Emeka Obi")
        results = run_rules(record, [rule])
        assert results[0]["status"] == "pass"

    def test_required_field_missing_fails(self):
        rule = FakeRule("r1", "Full name required", "required", "Full Name")
        results = run_rules({}, [rule])
        assert results[0]["status"] == "fail"

    def test_required_null_value_fails(self):
        rule = FakeRule("r1", "Full name required", "required", "Full Name")
        record = _record("Full Name", None, null=True)
        results = run_rules(record, [rule])
        assert results[0]["status"] == "fail"

    def test_disabled_rule_is_skipped(self):
        rule = FakeRule(
            "r1", "Full name required", "required", "Full Name", enabled=False
        )
        results = run_rules({}, [rule])
        assert results[0]["status"] == "skip"


class TestFormatRules:
    def test_valid_nin_format_passes(self):
        rule = FakeRule("r2", "NIN format", "format", "NIN", pattern=r"^\d{11}$")
        record = _record("NIN", "12345678901")
        results = run_rules(record, [rule])
        assert results[0]["status"] == "pass"

    def test_invalid_nin_format_fails(self):
        rule = FakeRule("r2", "NIN format", "format", "NIN", pattern=r"^\d{11}$")
        record = _record("NIN", "1234")
        results = run_rules(record, [rule])
        assert results[0]["status"] == "fail"

    def test_format_rule_skipped_when_field_missing(self):
        rule = FakeRule("r2", "NIN format", "format", "NIN", pattern=r"^\d{11}$")
        results = run_rules({}, [rule])
        assert results[0]["status"] == "skip"


class TestLogicalRules:
    def test_dob_not_in_future_passes(self):
        rule = FakeRule(
            "r3", "DOB not in future", "logical", "Date of Birth", check="not_future"
        )
        record = _record("Date of Birth", "1990-03-15")
        results = run_rules(record, [rule])
        assert results[0]["status"] == "pass"

    def test_future_dob_fails(self):
        rule = FakeRule(
            "r3", "DOB not in future", "logical", "Date of Birth", check="not_future"
        )
        record = _record("Date of Birth", "2099-01-01")
        results = run_rules(record, [rule])
        assert results[0]["status"] == "fail"

    def test_adult_applicant_passes_min_age(self):
        rule = FakeRule(
            "r4", "Must be 18+", "logical", "Date of Birth", check="min_age_18"
        )
        record = _record("Date of Birth", "1990-01-01")
        results = run_rules(record, [rule])
        assert results[0]["status"] == "pass"

    def test_minor_fails_min_age(self):
        rule = FakeRule(
            "r4", "Must be 18+", "logical", "Date of Birth", check="min_age_18"
        )
        record = _record("Date of Birth", "2020-01-01")
        results = run_rules(record, [rule])
        assert results[0]["status"] == "fail"

    def test_valid_expiry_passes(self):
        rule = FakeRule(
            "r5", "Not expired", "logical", "Expiry Date", check="not_expired"
        )
        record = _record("Expiry Date", "2030-01-01")
        results = run_rules(record, [rule])
        assert results[0]["status"] == "pass"

    def test_expired_document_fails(self):
        rule = FakeRule(
            "r5", "Not expired", "logical", "Expiry Date", check="not_expired"
        )
        record = _record("Expiry Date", "2000-01-01")
        results = run_rules(record, [rule])
        assert results[0]["status"] == "fail"

    def test_unparseable_date_warns(self):
        rule = FakeRule(
            "r3", "DOB not in future", "logical", "Date of Birth", check="not_future"
        )
        record = _record("Date of Birth", "not-a-date")
        results = run_rules(record, [rule])
        assert results[0]["status"] == "warn"


class TestCrossDocRules:
    def test_consistent_values_pass(self):
        rule = FakeRule("r6", "Name consistent", "cross_doc", "Full Name")
        record = {
            "Full Name": {
                "bestValue": "Emeka Obi",
                "hasConflict": False,
                "isNull": False,
                "allValues": [
                    {"value": "Emeka Obi"},
                    {"value": "Emeka Obi"},
                ],
            }
        }
        results = run_rules(record, [rule])
        assert results[0]["status"] == "pass"

    def test_conflicting_values_fail(self):
        rule = FakeRule("r6", "Name consistent", "cross_doc", "Full Name")
        record = {
            "Full Name": {
                "bestValue": "Emeka Obi",
                "hasConflict": True,
                "isNull": False,
                "allValues": [
                    {"value": "Emeka Obi"},
                    {"value": "Emmanuel Obi"},
                ],
            }
        }
        results = run_rules(record, [rule])
        assert results[0]["status"] == "fail"
        assert "Emeka Obi" in results[0]["message"]
