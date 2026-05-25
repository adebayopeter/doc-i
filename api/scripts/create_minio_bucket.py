"""
Create the MinIO documents bucket on first run.

Run once after starting services:
    docker compose exec api python scripts/create_minio_bucket.py

Safe to run multiple times — skips creation if bucket already exists.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def create_bucket() -> None:
    from config.logging import get_logger
    from config.settings import settings
    from services.storage import ensure_bucket

    logger = get_logger(__name__)

    try:
        ensure_bucket()
        print(
            f"\n✅ MinIO bucket ready\n"
            f"   Bucket:   {settings.MINIO_BUCKET}\n"
            f"   Endpoint: {settings.MINIO_ENDPOINT}\n"
        )
        logger.info(
            f"MinIO bucket ready: {settings.MINIO_BUCKET} "
            f"at {settings.MINIO_ENDPOINT}"
        )
    except Exception as e:
        logger.error(f"Could not create MinIO bucket: {e}")
        print(
            f"\n❌ MinIO bucket creation failed: {e}\n"
            f"   Is MinIO running? Check: docker compose ps minio\n"
        )
        sys.exit(1)


if __name__ == "__main__":
    create_bucket()
