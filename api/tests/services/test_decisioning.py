"""
Tests for the decisioning service.
"""

from services.decisioning import compute_decision

THRESHOLDS = {"autoAbove": 85, "manualBelow": 60}


def _record(field, value, confidence, conflict=False):
    return {
        field: {
            "bestValue": value,
            "bestConfidence": confidence,
            "hasConflict": conflict,
            "isNull": value is None,
        }
    }


class TestComputeDecision:
    def test_all_high_confidence_is_auto(self):
        record = {
            "Full Name": {
                "bestValue": "Emeka Obi",
                "bestConfidence": 95,
                "hasConflict": False,
                "isNull": False,
            },
            "NIN": {
                "bestValue": "12345678901",
                "bestConfidence": 99,
                "hasConflict": False,
                "isNull": False,
            },
        }
        result = compute_decision(record, [], THRESHOLDS)
        assert result["overallDecision"] == "auto"

    def test_low_confidence_field_triggers_manual(self):
        record = {
            "Full Name": {
                "bestValue": "Emeka Obi",
                "bestConfidence": 40,
                "hasConflict": False,
                "isNull": False,
            },
        }
        result = compute_decision(record, [], THRESHOLDS)
        assert result["overallDecision"] == "manual"

    def test_medium_confidence_triggers_review(self):
        record = {
            "Full Name": {
                "bestValue": "Emeka Obi",
                "bestConfidence": 72,
                "hasConflict": False,
                "isNull": False,
            },
        }
        result = compute_decision(record, [], THRESHOLDS)
        assert result["overallDecision"] == "review"

    def test_validation_failure_triggers_manual(self):
        record = {
            "Full Name": {
                "bestValue": "Emeka Obi",
                "bestConfidence": 95,
                "hasConflict": False,
                "isNull": False,
            },
        }
        failures = [{"status": "fail", "name": "NIN required"}]
        result = compute_decision(record, failures, THRESHOLDS)
        assert result["overallDecision"] == "manual"

    def test_conflict_triggers_review(self):
        record = {
            "Full Name": {
                "bestValue": "Emeka Obi",
                "bestConfidence": 90,
                "hasConflict": True,
                "isNull": False,
            },
        }
        result = compute_decision(record, [], THRESHOLDS)
        assert result["overallDecision"] == "review"

    def test_summary_counts_are_correct(self):
        record = {
            "Field A": {
                "bestValue": "v",
                "bestConfidence": 95,
                "hasConflict": False,
                "isNull": False,
            },
            "Field B": {
                "bestValue": "v",
                "bestConfidence": 72,
                "hasConflict": False,
                "isNull": False,
            },
            "Field C": {
                "bestValue": "v",
                "bestConfidence": 40,
                "hasConflict": False,
                "isNull": False,
            },
        }
        result = compute_decision(record, [], THRESHOLDS)
        assert result["summary"]["auto"] == 1
        assert result["summary"]["review"] == 1
        assert result["summary"]["manual"] == 1

    def test_field_decisions_are_sorted_by_confidence(self):
        record = {
            "Field A": {
                "bestValue": "v",
                "bestConfidence": 95,
                "hasConflict": False,
                "isNull": False,
            },
            "Field B": {
                "bestValue": "v",
                "bestConfidence": 40,
                "hasConflict": False,
                "isNull": False,
            },
        }
        result = compute_decision(record, [], THRESHOLDS)
        confidences = [f["confidence"] for f in result["fieldDecisions"]]
        assert confidences == sorted(confidences)

    def test_empty_record_returns_auto(self):
        result = compute_decision({}, [], THRESHOLDS)
        assert result["overallDecision"] == "auto"
        assert result["summary"]["auto"] == 0

    def test_thresholds_are_included_in_response(self):
        result = compute_decision({}, [], THRESHOLDS)
        assert result["thresholds"]["autoAbove"] == 85
        assert result["thresholds"]["manualBelow"] == 60

    def test_custom_thresholds_are_applied(self):
        record = {
            "Full Name": {
                "bestValue": "Emeka Obi",
                "bestConfidence": 75,
                "hasConflict": False,
                "isNull": False,
            },
        }
        # Lower the auto threshold — 75 should now be auto
        result = compute_decision(record, [], {"autoAbove": 70, "manualBelow": 50})
        assert result["overallDecision"] == "auto"
