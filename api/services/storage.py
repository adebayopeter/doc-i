"""
MinIO — on-premises S3-compatible document storage.
Stores raw uploaded files and returns object keys for DB references.
"""

import io
import uuid

from minio import Minio

from config.logging import get_logger

logger = get_logger(__name__)


def _client() -> Minio:
    """Create a MinIO client from settings."""
    from config.settings import settings

    return Minio(
        settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_USER,
        secret_key=settings.MINIO_PASSWORD,
        secure=settings.MINIO_SECURE,
    )


def ensure_bucket() -> None:
    """Create the documents bucket if it does not exist."""
    from config.settings import settings

    client = _client()
    if not client.bucket_exists(settings.MINIO_BUCKET):
        client.make_bucket(settings.MINIO_BUCKET)
        logger.info(f"Created MinIO bucket: {settings.MINIO_BUCKET}")
    else:
        logger.debug(f"MinIO bucket already exists: {settings.MINIO_BUCKET}")


def upload_file(
    file_bytes: bytes,
    filename: str,
    mime_type: str,
    submission_id: str,
) -> str:
    """
    Upload file bytes to MinIO.
    Returns the object key used to retrieve or delete the file later.
    """
    from config.settings import settings

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    object_key = f"{submission_id}/{uuid.uuid4().hex}.{ext}"

    _client().put_object(
        settings.MINIO_BUCKET,
        object_key,
        io.BytesIO(file_bytes),
        length=len(file_bytes),
        content_type=mime_type,
    )
    logger.debug(f"Uploaded file to MinIO: {object_key} ({len(file_bytes)} bytes)")
    return object_key


def get_file(object_key: str) -> bytes:
    """Download a file from MinIO. Returns raw bytes."""
    from config.settings import settings

    response = _client().get_object(settings.MINIO_BUCKET, object_key)
    data = response.read()
    logger.debug(f"Downloaded file from MinIO: {object_key}")
    return data


def delete_file(object_key: str) -> None:
    """Delete a file from MinIO storage."""
    from config.settings import settings

    client = _client()
    client.remove_object(settings.MINIO_BUCKET, object_key)
    logger.debug(f"Deleted file: {object_key}")
