"""
Tests for the aggregation service.
"""

from services.aggregation import build_unified_record, get_field_value


class FakeDocument:
    """Minimal fake SubmissionDocument for testing."""

    def __init__(self, doc_id: str, doc_type: str, fields: dict):
        self.id = doc_id
        self.document_type = doc_type
        self.filename = f"{doc_id}.pdf"
        self.extracted_fields = fields


class TestBuildUnifiedRecord:
    def test_empty_documents_returns_empty_record(self):
        assert build_unified_record([]) == {}

    def test_single_document_single_field(self):
        docs = [
            FakeDocument(
                "doc_1",
                "NIN slip",
                {"Full Name": {"value": "Emeka Obi", "confidence": 90}},
            )
        ]
        record = build_unified_record(docs)

        assert "Full Name" in record
        assert record["Full Name"]["bestValue"] == "Emeka Obi"
        assert record["Full Name"]["bestConfidence"] == 90
        assert record["Full Name"]["isNull"] is False
        assert record["Full Name"]["hasConflict"] is False

    def test_picks_highest_confidence_value(self):
        docs = [
            FakeDocument(
                "doc_1",
                "NIN slip",
                {"Full Name": {"value": "Emeka Obi", "confidence": 95}},
            ),
            FakeDocument(
                "doc_2",
                "Bank statement",
                {"Full Name": {"value": "E. Obi", "confidence": 60}},
            ),
        ]
        record = build_unified_record(docs)

        assert record["Full Name"]["bestValue"] == "Emeka Obi"
        assert record["Full Name"]["bestConfidence"] == 95
        assert record["Full Name"]["sourceDocId"] == "doc_1"

    def test_detects_conflict_on_different_values(self):
        docs = [
            FakeDocument(
                "doc_1",
                "NIN slip",
                {"Full Name": {"value": "Emeka Obi", "confidence": 95}},
            ),
            FakeDocument(
                "doc_2",
                "Bank statement",
                {"Full Name": {"value": "Emmanuel Obi", "confidence": 88}},
            ),
        ]
        record = build_unified_record(docs)

        assert record["Full Name"]["hasConflict"] is True

    def test_no_conflict_when_values_match(self):
        docs = [
            FakeDocument(
                "doc_1",
                "NIN slip",
                {"Full Name": {"value": "Emeka Obi", "confidence": 95}},
            ),
            FakeDocument(
                "doc_2",
                "Payslip",
                {"Full Name": {"value": "Emeka Obi", "confidence": 88}},
            ),
        ]
        record = build_unified_record(docs)

        assert record["Full Name"]["hasConflict"] is False

    def test_tracks_all_source_values(self):
        docs = [
            FakeDocument(
                "doc_1",
                "NIN slip",
                {"Full Name": {"value": "Emeka Obi", "confidence": 95}},
            ),
            FakeDocument(
                "doc_2",
                "Bank statement",
                {"Full Name": {"value": "E. Obi", "confidence": 60}},
            ),
        ]
        record = build_unified_record(docs)

        assert len(record["Full Name"]["allValues"]) == 2

    def test_null_value_marked_as_null(self):
        docs = [
            FakeDocument(
                "doc_1",
                "NIN slip",
                {"Full Name": {"value": None, "confidence": 0}},
            )
        ]
        record = build_unified_record(docs)

        assert record["Full Name"]["isNull"] is True

    def test_multiple_fields_aggregated(self):
        docs = [
            FakeDocument(
                "doc_1",
                "NIN slip",
                {
                    "Full Name": {"value": "Emeka Obi", "confidence": 95},
                    "NIN": {"value": "12345678901", "confidence": 99},
                },
            )
        ]
        record = build_unified_record(docs)

        assert "Full Name" in record
        assert "NIN" in record

    def test_document_with_no_fields_is_skipped(self):
        docs = [
            FakeDocument("doc_1", "Unknown", {}),
            FakeDocument(
                "doc_2",
                "NIN slip",
                {"Full Name": {"value": "Emeka Obi", "confidence": 90}},
            ),
        ]
        record = build_unified_record(docs)

        assert "Full Name" in record
        assert len(record) == 1


class TestGetFieldValue:
    def test_returns_best_value(self):
        record = {
            "Full Name": {
                "bestValue": "Emeka Obi",
                "bestConfidence": 95,
                "isNull": False,
            }
        }
        assert get_field_value(record, "Full Name") == "Emeka Obi"

    def test_returns_none_for_missing_field(self):
        assert get_field_value({}, "Full Name") is None

    def test_returns_none_for_null_field(self):
        record = {
            "Full Name": {
                "bestValue": None,
                "bestConfidence": 0,
                "isNull": True,
            }
        }
        assert get_field_value(record, "Full Name") is None
