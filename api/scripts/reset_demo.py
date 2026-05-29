"""
Reset demo data — wipes all submissions, documents, processes and categories.
Keeps validation rules (re-seeds them) and thresholds (resets to default).
Run with: docker compose exec api python scripts/reset_demo.py

Use --hard to also wipe validation rules and thresholds.
"""

import sys


def reset_demo(db, hard: bool = False):
    from db.models import (
        AuditLog,
        DocumentCategory,
        Process,
        ProcessThreshold,
        Submission,
        SubmissionDocument,
    )
    from services.decisioning import DEFAULT_THRESHOLDS

    print("🗑️  Resetting demo data...")

    # Order matters — delete children before parents
    deleted_docs = db.query(SubmissionDocument).delete(synchronize_session=False)
    print(f"   Deleted {deleted_docs} submission documents")

    deleted_logs = db.query(AuditLog).delete(synchronize_session=False)
    print(f"   Deleted {deleted_logs} audit logs")

    deleted_subs = db.query(Submission).delete(synchronize_session=False)
    print(f"   Deleted {deleted_subs} submissions")

    deleted_procs = db.query(Process).delete(synchronize_session=False)
    print(f"   Deleted {deleted_procs} processes (cascades documents + fields)")

    deleted_cats = db.query(DocumentCategory).delete(synchronize_session=False)
    print(f"   Deleted {deleted_cats} document categories")

    # Reset thresholds to default
    db.query(ProcessThreshold).delete(synchronize_session=False)
    global_threshold = ProcessThreshold(
        process_id=None,
        auto_above=DEFAULT_THRESHOLDS["autoAbove"],
        manual_below=DEFAULT_THRESHOLDS["manualBelow"],
    )
    db.add(global_threshold)
    print(
        f"   Reset global thresholds to "
        f"auto≥{DEFAULT_THRESHOLDS['autoAbove']}% "
        f"manual<{DEFAULT_THRESHOLDS['manualBelow']}%"
    )

    if hard:
        from db.models import ValidationRule

        deleted_rules = db.query(ValidationRule).delete(synchronize_session=False)
        print(f"   Deleted {deleted_rules} validation rules (hard reset)")

    db.commit()
    print("   ✅ Database reset complete")

    if hard:
        print("\n🌱 Re-seeding validation rules...")
        from scripts.seed_rules import seed

        seed(reset=True, session=db)


if __name__ == "__main__":
    from db.session import SessionLocal

    hard = "--hard" in sys.argv

    if hard:
        print("⚠️  HARD RESET — this will also wipe and re-seed validation rules.")
    else:
        print(
            "ℹ️  Soft reset — keeps validation rules. " "Use --hard to also reset rules."
        )

    confirm = input("Type 'yes' to confirm: ").strip().lower()
    if confirm != "yes":
        print("Aborted.")
        sys.exit(0)

    db = SessionLocal()
    try:
        reset_demo(db, hard=hard)
    finally:
        db.close()

    print("\n✅ Demo reset complete. Ready for a fresh run.")
    print("\nNext steps:")
    print("  1. Go to http://localhost:8503")
    print("  2. Config → Add categories")
    print("  3. Processes → Create process + configure fields")
    print("  4. Submissions → Open a submission")
    print("  5. Documents → Upload documents")
    print("  6. Analysis → View results")
