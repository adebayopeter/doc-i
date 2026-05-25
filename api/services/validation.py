"""
Validation engine — runs configurable rules against the unified record.

Rule types:
  required   — field must be present and non-null
  format     — field value must match a regex pattern
  logical    — field must satisfy a date/age/expiry check
  cross_doc  — field value must be consistent across all source documents
"""

import re
from datetime import datetime, timezone
from typing import Any, Dict, List

from config.logging import get_logger

logger = get_logger(__name__)


def run_rules(
    unified_record: Dict[str, Any],
    rules: list,
) -> List[Dict]:
    """
    Run all enabled validation rules against the unified record.

    Args:
        unified_record: Output of aggregation.build_unified_record()
        rules:          List of ValidationRule ORM objects

    Returns:
        List of result dicts:
        {
            "ruleId": "rule_r01",
            "name": "Full name required",
            "type": "required",
            "field": "Full Name",
            "severity": "error",
            "status": "pass|fail|warn|skip",
            "message": "Full Name present — Emeka Obi"
        }
    """
    results = []

    for rule in rules:
        if not rule.is_enabled:
            results.append(_result(rule, "skip", "Rule disabled"))
            continue

        field_data = unified_record.get(rule.field)

        if rule.rule_type == "required":
            results.append(_check_required(rule, field_data))

        elif rule.rule_type == "format":
            results.append(_check_format(rule, field_data))

        elif rule.rule_type == "logical":
            results.append(_check_logical(rule, field_data))

        elif rule.rule_type == "cross_doc":
            results.append(_check_cross_doc(rule, field_data))

        else:
            results.append(
                _result(rule, "skip", f"Unknown rule type: {rule.rule_type}")
            )

    passed = sum(1 for r in results if r["status"] == "pass")
    failed = sum(1 for r in results if r["status"] == "fail")
    logger.debug(f"Validation: {passed} passed, {failed} failed")

    return results


def _check_required(rule: Any, field_data: Any) -> Dict:
    """Field must be present and non-null."""
    if not field_data or field_data.get("isNull") or not field_data.get("bestValue"):
        return _result(rule, "fail", f"{rule.field} is missing from all documents")
    value_preview = str(field_data["bestValue"])[:40]
    return _result(rule, "pass", f'{rule.field} present — "{value_preview}"')


def _check_format(rule: Any, field_data: Any) -> Dict:
    """Field value must match the configured regex pattern."""
    if not field_data or not field_data.get("bestValue"):
        return _result(rule, "skip", f"{rule.field} not found in any document")

    value = str(field_data["bestValue"])
    # Strip common formatting characters before pattern matching
    clean_value = value.replace(",", "").replace("₦", "").replace(" ", "").strip()

    try:
        pattern = re.compile(rule.pattern)
        matches = pattern.match(value) or pattern.match(clean_value)
    except re.error as e:
        return _result(rule, "skip", f"Invalid pattern in rule: {e}")

    if matches:
        return _result(rule, "pass", f'Format valid: "{value}"')
    return _result(rule, "fail", f'Format invalid: "{value}"')


def _check_logical(rule: Any, field_data: Any) -> Dict:
    """Date/age/expiry logical checks."""
    if not field_data or not field_data.get("bestValue"):
        return _result(rule, "skip", f"{rule.field} not found in any document")

    value = str(field_data["bestValue"])

    # Parse the date value
    parsed_date = None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            parsed_date = datetime.strptime(value, fmt)
            break
        except ValueError:
            continue

    if not parsed_date:
        return _result(rule, "warn", f'Cannot parse date: "{value}"')

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    age_years = (now - parsed_date).days // 365

    check = rule.check

    if check == "not_future":
        if parsed_date > now:
            return _result(rule, "fail", f'Date is in the future: "{value}"')
        return _result(rule, "pass", f'Date is valid: "{value}"')

    if check == "min_age_18":
        if age_years < 18:
            return _result(
                rule, "fail", f"Applicant is {age_years} years old — must be 18 or over"
            )
        return _result(rule, "pass", f"Applicant age: {age_years} years")

    if check == "max_age_75":
        if age_years >= 75:
            return _result(
                rule,
                "warn",
                f"Applicant is {age_years} years old — over 75, manual review recommended",
            )
        return _result(rule, "pass", f"Applicant age: {age_years} years")

    if check == "not_expired":
        if parsed_date < now:
            return _result(rule, "fail", f'Document expired: "{value}"')
        return _result(rule, "pass", f'Document valid until: "{value}"')

    return _result(rule, "skip", f'Unknown check type: "{check}"')


def _check_cross_doc(rule: Any, field_data: Any) -> Dict:
    """Field value must be consistent across all source documents."""
    if not field_data:
        return _result(rule, "skip", f"{rule.field} not found in any document")

    if not field_data.get("hasConflict"):
        n = len(field_data.get("allValues", []))
        return _result(rule, "pass", f"{rule.field} is consistent across {n} source(s)")

    conflicting = list(
        {v["value"] for v in field_data.get("allValues", []) if v["value"]}
    )
    values_str = " vs ".join(f'"{v}"' for v in conflicting)
    return _result(rule, "fail", f"Conflicting values across documents: {values_str}")


def _result(rule: Any, status: str, message: str) -> Dict:
    """Build a standardised result dict."""
    return {
        "ruleId": rule.id,
        "name": rule.name,
        "type": rule.rule_type,
        "field": rule.field,
        "severity": rule.severity,
        "status": status,
        "message": message,
    }
