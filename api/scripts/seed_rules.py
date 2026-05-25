"""
Seed default Nigerian document validation rules.

Run once after the first migration:
    docker compose exec api python scripts/seed_rules.py

Rules are idempotent — running twice will not create duplicates.
Each rule has a fixed ID so re-running skips rules that already exist.

To reset all rules:
    docker compose exec api python scripts/seed_rules.py --reset
"""

import os
import sys

# Ensure api/ is on the path when run directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def seed(reset: bool = False) -> None:
    from config.logging import get_logger
    from db.models import ValidationRule
    from db.session import SessionLocal

    logger = get_logger(__name__)
    db = SessionLocal()

    # ── Default rules ──────────────────────────────────────────────────────
    # Nigerian-specific rules — NIN and BVN are 11-digit numbers,
    # account numbers are 10 digits (NUBAN format)
    DEFAULT_RULES = [
        # ── Required field rules ───────────────────────────────────────────
        {
            "id": "rule_default_r01",
            "name": "Full name required",
            "rule_type": "required",
            "field": "Full Name",
            "severity": "error",
        },
        {
            "id": "rule_default_r02",
            "name": "Date of birth required",
            "rule_type": "required",
            "field": "Date of Birth",
            "severity": "error",
        },
        {
            "id": "rule_default_r06",
            "name": "Address required",
            "rule_type": "required",
            "field": "Address",
            "severity": "error",
        },
        {
            "id": "rule_default_r12",
            "name": "Employer name required",
            "rule_type": "required",
            "field": "Employer Name",
            "severity": "warning",
        },
        # ── Logical rules ──────────────────────────────────────────────────
        {
            "id": "rule_default_r03",
            "name": "Date of birth not in future",
            "rule_type": "logical",
            "field": "Date of Birth",
            "check": "not_future",
            "severity": "error",
        },
        {
            "id": "rule_default_r04",
            "name": "Applicant aged 18 or over",
            "rule_type": "logical",
            "field": "Date of Birth",
            "check": "min_age_18",
            "severity": "error",
        },
        {
            "id": "rule_default_r05",
            "name": "Applicant under 75",
            "rule_type": "logical",
            "field": "Date of Birth",
            "check": "max_age_75",
            "severity": "warning",
        },
        {
            "id": "rule_default_r07",
            "name": "Document not expired",
            "rule_type": "logical",
            "field": "Expiry Date",
            "check": "not_expired",
            "severity": "error",
        },
        # ── Format rules — Nigerian document standards ─────────────────────
        {
            "id": "rule_default_r09",
            "name": "NIN format (11 digits)",
            "rule_type": "format",
            "field": "NIN",
            "pattern": r"^\d{11}$",
            "severity": "error",
        },
        {
            "id": "rule_default_r10",
            "name": "BVN format (11 digits)",
            "rule_type": "format",
            "field": "BVN",
            "pattern": r"^\d{11}$",
            "severity": "error",
        },
        {
            "id": "rule_default_r11",
            "name": "Account number format (NUBAN — 10 digits)",
            "rule_type": "format",
            "field": "Account Number",
            "pattern": r"^\d{10}$",
            "severity": "warning",
        },
        # ── Cross-document consistency rules ───────────────────────────────
        {
            "id": "rule_default_r08",
            "name": "Full name consistent across documents",
            "rule_type": "cross_doc",
            "field": "Full Name",
            "severity": "error",
        },
    ]

    try:
        if reset:
            logger.warning("Resetting all default validation rules...")
            deleted = (
                db.query(ValidationRule)
                .filter(ValidationRule.id.like("rule_default_%"))
                .delete(synchronize_session=False)
            )
            db.commit()
            logger.info(f"Deleted {deleted} existing default rules")

        added = 0
        skipped = 0

        for rule_data in DEFAULT_RULES:
            existing = (
                db.query(ValidationRule)
                .filter(ValidationRule.id == rule_data["id"])
                .first()
            )
            if existing:
                skipped += 1
                continue

            db.add(ValidationRule(**rule_data))
            added += 1

        db.commit()

        logger.info(f"Seed complete — {added} rules added, {skipped} already existed")
        print(
            f"\n✅ Seed complete\n"
            f"   Added:   {added} rules\n"
            f"   Skipped: {skipped} rules (already existed)\n"
            f"   Total:   {len(DEFAULT_RULES)} default rules\n"
        )

    except Exception as e:
        db.rollback()
        logger.error(f"Seed failed: {e}")
        print(f"\n❌ Seed failed: {e}\n")
        sys.exit(1)

    finally:
        db.close()


if __name__ == "__main__":
    reset_flag = "--reset" in sys.argv
    seed(reset=reset_flag)
