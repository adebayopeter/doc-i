"""
Decisioning service — confidence-based routing.

Routes each extracted field and the overall submission to one of:
  auto   — confidence ≥ high threshold, process automatically
  review — confidence between low and high thresholds, flag for review
  manual — confidence < low threshold, require manual input

Overall submission decision is the worst-case across all fields.
"""

from typing import Any, Dict, List

from config.logging import get_logger

logger = get_logger(__name__)

# ── Default thresholds ─────────────────────────────────────────────────────
# Configurable via PUT /v1/config/thresholds
DEFAULT_THRESHOLDS = {
    "autoAbove": 85,
    "manualBelow": 60,
}


def compute_decision(
    unified_record: Dict[str, Any],
    validation_results: List[Dict],
    thresholds: Dict = None,
) -> Dict[str, Any]:
    """
    Compute the routing decision for a submission.

    Args:
        unified_record:      Output of aggregation.build_unified_record()
        validation_results:  Output of validation.run_rules()
        thresholds:          Optional custom thresholds dict

    Returns:
        {
            "overallDecision": "auto|review|manual",
            "reason": "...",
            "thresholds": {"autoAbove": 85, "manualBelow": 60},
            "summary": {"auto": 8, "review": 2, "manual": 1},
            "fieldDecisions": [...]
        }
    """
    t = thresholds or DEFAULT_THRESHOLDS
    high = t.get("autoAbove", 85)
    low = t.get("manualBelow", 60)

    # ── Per-field decisions ────────────────────────────────────────────────
    field_decisions = []
    for field, data in unified_record.items():
        conf = data.get("bestConfidence", 0)

        if conf >= high:
            decision = "auto"
        elif conf >= low:
            decision = "review"
        else:
            decision = "manual"

        field_decisions.append(
            {
                "field": field,
                "value": data.get("bestValue"),
                "confidence": conf,
                "decision": decision,
                "hasConflict": data.get("hasConflict", False),
                "isMissing": data.get("isNull", True),
            }
        )

    # ── Summary counts ─────────────────────────────────────────────────────
    auto_count = sum(1 for f in field_decisions if f["decision"] == "auto")
    review_count = sum(1 for f in field_decisions if f["decision"] == "review")
    manual_count = sum(1 for f in field_decisions if f["decision"] == "manual")

    # ── Overall decision ───────────────────────────────────────────────────
    validation_failures = [r for r in validation_results if r["status"] == "fail"]
    conflicts = [f for f in field_decisions if f["hasConflict"]]
    manual_fields = [f for f in field_decisions if f["decision"] == "manual"]

    if manual_fields or validation_failures:
        overall = "manual"
        reason = (
            f"{len(manual_fields)} field(s) require manual input; "
            f"{len(validation_failures)} validation failure(s)"
        )
    elif conflicts or review_count > len(field_decisions) * 0.25:
        overall = "review"
        reason = f"{len(conflicts)} conflict(s) detected; " f"senior review recommended"
    else:
        overall = "auto"
        reason = "All fields meet the auto-process confidence threshold"

    logger.info(
        f"Decision: {overall} — "
        f"auto={auto_count}, review={review_count}, manual={manual_count}"
    )

    return {
        "overallDecision": overall,
        "reason": reason,
        "thresholds": {"autoAbove": high, "manualBelow": low},
        "summary": {
            "auto": auto_count,
            "review": review_count,
            "manual": manual_count,
        },
        "fieldDecisions": sorted(field_decisions, key=lambda x: x["confidence"]),
    }
