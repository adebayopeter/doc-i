import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from db.session import Base


# Helper
def _gen_id(prefix: str) -> str:
    """Generates a short readable ID e.g. proc_a1b2c3d4e5f6"""
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _now():
    return datetime.now(timezone.utc)


# 1. Process
class Process(Base):
    """
    A reusable workflow definition — e.g. RSA Mortgage, Benefit Application.
    Defines which documents are required for that workflow.
    """

    __tablename__ = "processes"

    id = Column(String, primary_key=True, default=lambda: _gen_id("proc"))
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    color_var = Column(String(50), default="info")
    icon = Column(String(100), default="ti-file")
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )

    # relationships
    documents = relationship(
        "ProcessDocument",
        back_populates="process",
        cascade="all, delete-orphan",
        order_by="ProcessDocument.sort_order",
    )
    submissions = relationship("Submission", back_populates="process")
    extraction_fields = relationship(
        "ProcessExtractionField",
        back_populates="process",
        cascade="all, delete-orphan",
        order_by="ProcessExtractionField.sort_order",
    )

    def __repr__(self):
        return f"<Process id={self.id} name={self.name}>"


# 2. ProcessDocument
class ProcessDocument(Base):
    """
    One required document within a process checklist.
    e.g. "NIN slip", "Bank statement (6 months)"
    """

    __tablename__ = "process_documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    process_id = Column(
        String, ForeignKey("processes.id", ondelete="CASCADE"), nullable=False
    )
    name = Column(String(300), nullable=False)
    category = Column(String(100), nullable=False)
    is_required = Column(Boolean, default=True, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)

    # relationships
    process = relationship("Process", back_populates="documents")
    extraction_fields = relationship(
        "ProcessDocumentField",
        back_populates="process_document",
        cascade="all, delete-orphan",
        order_by="ProcessDocumentField.sort_order",
    )

    def __repr__(self):
        return f"<ProcessDocument id={self.id} name={self.name}>"


class ProcessDocumentField(Base):
    """
    Per-document field configuration for AI extraction and decisioning.

    Fields are tied to a specific document in the process checklist —
    not to the process as a whole. This means:
      - NIN Slip extracts: Full Name, NIN, Date of Birth, Expiry Date
      - Bank Statement extracts: Full Name, Account Number, Bank Name
      - Each document knows exactly what it should contain

    If a document in the checklist has no active fields, it will be
    classified (document type identified) but no fields will be extracted.

    If NO document in a process has any fields configured, classification
    is disabled entirely for that process.
    """

    __tablename__ = "process_document_fields"

    id = Column(
        String,
        primary_key=True,
        default=lambda: _gen_id("pdf"),
    )
    process_document_id = Column(
        Integer,
        ForeignKey("process_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(String(200), nullable=False)
    description = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    include_in_decision = Column(Boolean, default=True, nullable=False)
    null_is_manual = Column(Boolean, default=False, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)

    # relationships
    process_document = relationship(
        "ProcessDocument", back_populates="extraction_fields"
    )

    __table_args__ = (
        UniqueConstraint(
            "process_document_id",
            "name",
            name="uq_process_document_field_name",
        ),
    )

    def __repr__(self):
        return (
            f"<ProcessDocumentField id={self.id} "
            f"doc={self.process_document_id} name={self.name}>"
        )


class ProcessExtractionField(Base):
    """
    Per-process field configuration for AI extraction and decisioning.

    If a process has no active extraction fields, classification
    is disabled — documents are stored but not processed by AI.
    """

    __tablename__ = "process_extraction_fields"

    id = Column(String, primary_key=True, default=lambda: _gen_id("pef"))
    process_id = Column(
        String,
        ForeignKey("processes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    include_in_decision = Column(Boolean, default=True, nullable=False)
    null_is_manual = Column(Boolean, default=False, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)

    process = relationship("Process", back_populates="extraction_fields")

    __table_args__ = (
        UniqueConstraint("process_id", "name", name="uq_process_field_name"),
    )


# 3. Submission
class Submission(Base):
    """
    One application instance — e.g. one mortgage case for one applicant.
    All uploaded documents belong to a submission.
    """

    __tablename__ = "submissions"

    id = Column(String, primary_key=True, default=lambda: _gen_id("sub"))
    process_id = Column(String, ForeignKey("processes.id"), nullable=False)
    reference = Column(String(200), nullable=True)  # your internal case ref
    applicant_id = Column(String(200), nullable=True)  # your system's user ID
    status = Column(String(50), default="open", nullable=False)
    # status values: open | in_progress | complete | rejected
    meta_data = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )

    # relationships
    process = relationship("Process", back_populates="submissions")
    documents = relationship(
        "SubmissionDocument",
        back_populates="submission",
        cascade="all, delete-orphan",
    )
    audit_logs = relationship("AuditLog", back_populates="submission")

    def __repr__(self):
        return f"<Submission id={self.id} status={self.status}>"


# 4. SubmissionDocument
class SubmissionDocument(Base):
    """
    One uploaded file within a submission.
    Stores the OCR result, AI classification, extracted fields,
    and the path to the raw file in MinIO.
    """

    __tablename__ = "submission_documents"

    id = Column(String, primary_key=True, default=lambda: _gen_id("doc"))
    submission_id = Column(
        String, ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False
    )
    filename = Column(String(500), nullable=False)
    storage_path = Column(String(1000), nullable=True)  # MinIO object key
    mime_type = Column(String(100), nullable=True)

    # Processing status
    # uploaded → processing → classified → failed
    status = Column(String(50), default="uploaded", nullable=False)

    # AI classification results
    document_type = Column(String(300), nullable=True)
    matched_doc_id = Column(Integer, nullable=True)  # ProcessDocument.id
    overall_confidence = Column(Float, nullable=True)

    # Extracted data
    # {
    #   "Full Name":   {"value": "Emeka Obi",   "confidence": 94},
    #   "NIN":         {"value": "12345678901", "confidence": 97}
    # }
    extracted_fields = Column(JSON, default=dict, nullable=False)

    # [{"type": "ok|warn|err", "message": "..."}]
    flags = Column(JSON, default=list, nullable=False)

    summary = Column(Text, nullable=True)
    raw_ocr_text = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )

    # relationships
    submission = relationship("Submission", back_populates="documents")

    def __repr__(self):
        return f"<SubmissionDocument id={self.id} status={self.status}>"


# 5. ValidationRule
class ValidationRule(Base):
    """
    Configurable validation rule — stored in the database so rules
    can be toggled on/off without redeploying the application.
    """

    __tablename__ = "validation_rules"

    id = Column(String, primary_key=True, default=lambda: _gen_id("rule"))
    name = Column(String(200), nullable=False)

    # rule_type values: required | format | logical | cross_doc
    rule_type = Column(String(50), nullable=False)

    # the field this rule checks e.g. "Full Name", "NIN", "Date of Birth"
    field = Column(String(200), nullable=False)

    # for logical rules: not_future | min_age_18 | max_age_75 | not_expired
    check = Column(String(100), nullable=True)

    # for format rules: regex pattern e.g. r"^\d{11}$" for NIN
    pattern = Column(String(500), nullable=True)

    # severity values: error | warning
    severity = Column(String(20), default="error", nullable=False)

    is_enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)

    def __repr__(self):
        return f"<ValidationRule id={self.id} name={self.name}>"


# 6. DocumentCategory
class DocumentCategory(Base):
    """
    Managed list of document categories.
    Used when configuring document checklists on processes.
    """

    __tablename__ = "document_categories"

    id = Column(String, primary_key=True, default=lambda: _gen_id("cat"))
    name = Column(String, nullable=False, unique=True)
    description = Column(String, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)


# 7. AuditLog
class AuditLog(Base):
    """
    Immutable record of every significant event on a submission.
    e.g. document uploaded, classified, decision overridden, status changed.
    Never update or delete audit log entries.
    """

    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    submission_id = Column(String, ForeignKey("submissions.id"), nullable=True)
    event = Column(String(100), nullable=False)
    # e.g. document.uploaded | document.classified | decision.overridden
    actor = Column(String(200), nullable=True)
    # who triggered this — user ID or "system"
    payload = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)

    # relationships
    submission = relationship("Submission", back_populates="audit_logs")

    def __repr__(self):
        return f"<AuditLog id={self.id} event={self.event}>"
