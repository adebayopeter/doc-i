"""
Tests that verify the database schema matches our SQLAlchemy models.
"""

from sqlalchemy import inspect


def test_all_tables_exist(test_engine):
    """All six model tables must exist in the database."""
    inspector = inspect(test_engine)
    tables = inspector.get_table_names()

    expected = {
        "processes",
        "process_documents",
        "submissions",
        "submission_documents",
        "validation_rules",
        "audit_logs",
    }
    for table in expected:
        assert table in tables, f"Table '{table}' is missing from database"


def test_processes_table_columns(test_engine):
    inspector = inspect(test_engine)
    columns = {c["name"] for c in inspector.get_columns("processes")}

    expected = {
        "id",
        "name",
        "description",
        "color_var",
        "icon",
        "is_active",
        "created_at",
        "updated_at",
    }
    assert expected.issubset(columns)


def test_submissions_table_columns(test_engine):
    inspector = inspect(test_engine)
    columns = {c["name"] for c in inspector.get_columns("submissions")}

    expected = {
        "id",
        "process_id",
        "reference",
        "applicant_id",
        "status",
        "meta_data",
        "created_at",
        "updated_at",
    }
    assert expected.issubset(columns)


def test_submission_documents_table_columns(test_engine):
    inspector = inspect(test_engine)
    columns = {c["name"] for c in inspector.get_columns("submission_documents")}

    expected = {
        "id",
        "submission_id",
        "filename",
        "storage_path",
        "mime_type",
        "status",
        "document_type",
        "matched_doc_id",
        "overall_confidence",
        "extracted_fields",
        "flags",
        "summary",
        "raw_ocr_text",
        "created_at",
        "updated_at",
    }
    assert expected.issubset(columns)


def test_validation_rules_table_columns(test_engine):
    inspector = inspect(test_engine)
    columns = {c["name"] for c in inspector.get_columns("validation_rules")}

    expected = {
        "id",
        "name",
        "rule_type",
        "field",
        "check",
        "pattern",
        "severity",
        "is_enabled",
        "created_at",
    }
    assert expected.issubset(columns)


def test_audit_logs_table_columns(test_engine):
    inspector = inspect(test_engine)
    columns = {c["name"] for c in inspector.get_columns("audit_logs")}

    expected = {
        "id",
        "submission_id",
        "event",
        "actor",
        "payload",
        "created_at",
    }
    assert expected.issubset(columns)


def test_process_documents_foreign_key(test_engine):
    inspector = inspect(test_engine)
    fks = inspector.get_foreign_keys("process_documents")
    fk_tables = [fk["referred_table"] for fk in fks]
    assert "processes" in fk_tables


def test_submissions_foreign_key(test_engine):
    inspector = inspect(test_engine)
    fks = inspector.get_foreign_keys("submissions")
    fk_tables = [fk["referred_table"] for fk in fks]
    assert "processes" in fk_tables


def test_submission_documents_foreign_key(test_engine):
    inspector = inspect(test_engine)
    fks = inspector.get_foreign_keys("submission_documents")
    fk_tables = [fk["referred_table"] for fk in fks]
    assert "submissions" in fk_tables
