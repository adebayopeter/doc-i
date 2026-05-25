"""
Aggregation service — merges extracted fields from multiple documents
into a single unified record per submission.

For each field:
  - Picks the value with the highest confidence as bestValue
  - Flags conflicts where different values appear across documents
  - Maintains full traceability to every source document
"""

from typing import Any, Dict

from config.logging import get_logger

logger = get_logger(__name__)


def build_unified_record(documents: list) -> Dict[str, Any]:
    """
    Merge extracted fields from all classified documents.

    Args:
        documents: List of SubmissionDocument ORM objects

    Returns:
        Dict mapping field names to their aggregated data:
        {
            "Full Name": {
                "bestValue": "Emeka Obi",
                "bestConfidence": 94,
                "sourceDocType": "National ID / NIN slip",
                "sourceDocId": "doc_r7tn4q12",
                "allValues": [...],
                "hasConflict": False,
                "isNull": False,
            }
        }
    """
    record: Dict[str, Any] = {}

    for doc in documents:
        if not doc.extracted_fields:
            continue

        for field, data in doc.extracted_fields.items():
            val = data.get("value") if isinstance(data, dict) else data
            conf = data.get("confidence", 0) if isinstance(data, dict) else 0

            if field not in record:
                record[field] = {
                    "bestValue": val,
                    "bestConfidence": conf,
                    "sourceDocType": doc.document_type,
                    "sourceDocId": doc.id,
                    "allValues": [],
                    "hasConflict": False,
                    "isNull": val is None,
                }

            # Add this source to allValues
            record[field]["allValues"].append(
                {
                    "value": val,
                    "confidence": conf,
                    "docType": doc.document_type,
                    "docId": doc.id,
                    "filename": doc.filename,
                }
            )

            # Promote to best if higher confidence
            if conf > record[field]["bestConfidence"]:
                record[field]["bestValue"] = val
                record[field]["bestConfidence"] = conf
                record[field]["sourceDocType"] = doc.document_type
                record[field]["sourceDocId"] = doc.id

            # Mark as non-null if any source has a value
            if val is not None:
                record[field]["isNull"] = False

            # Detect conflicts — values that differ across documents
            def _norm(v: Any) -> str:
                return str(v).lower().strip().replace(" ", "") if v else ""

            existing_best = record[field]["bestValue"]
            if (
                _norm(val)
                and _norm(existing_best)
                and _norm(val) != _norm(existing_best)
            ):
                record[field]["hasConflict"] = True

    conflict_count = sum(1 for f in record.values() if f["hasConflict"])
    logger.debug(
        f"Aggregated {len(record)} fields from {len(documents)} documents "
        f"({conflict_count} conflicts)"
    )
    return record


def get_field_value(record: Dict[str, Any], field: str) -> Any:
    """
    Convenience helper — get the best value for a field from the record.
    Returns None if field is not present or is null.
    """
    entry = record.get(field)
    if not entry or entry.get("isNull"):
        return None
    return entry.get("bestValue")
