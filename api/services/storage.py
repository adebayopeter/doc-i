"""
Storage service — file upload, retrieval and deletion.

Uses Cloudinary in production (CLOUDINARY_URL set) and
MinIO locally (MINIO_HOST set). Falls back gracefully.
"""

import os

from config.logging import get_logger

logger = get_logger(__name__)


def _get_backend():
    """Returns 'cloudinary' or 'minio' based on environment."""
    if os.getenv("CLOUDINARY_URL") or os.getenv("CLOUDINARY_CLOUD_NAME"):
        return "cloudinary"
    return "minio"


def upload_file(
    file_bytes: bytes,
    filename: str,
    mime_type: str,
    submission_id: str,
) -> str:
    """
    Upload a file and return its storage path/public_id.

    Returns:
        str: storage path — used to retrieve or delete the file later
    """
    backend = _get_backend()

    if backend == "cloudinary":
        return _cloudinary_upload(file_bytes, filename, mime_type, submission_id)
    return _minio_upload(file_bytes, filename, mime_type, submission_id)


def get_file(storage_path: str) -> bytes:
    """
    Retrieve a file by its storage path.

    Returns:
        bytes: raw file content
    """
    backend = _get_backend()

    if backend == "cloudinary":
        return _cloudinary_get(storage_path)
    return _minio_get(storage_path)


def delete_file(storage_path: str) -> None:
    """Delete a file from MinIO storage."""
    backend = _get_backend()

    if backend == "cloudinary":
        _cloudinary_delete(storage_path)
    else:
        _minio_delete(storage_path)


# ── Cloudinary backend ─────────────────────────────────────────────────────
def _cloudinary_upload(
    file_bytes: bytes,
    filename: str,
    mime_type: str,
    submission_id: str,
) -> str:
    import base64

    import cloudinary.uploader

    cloudinary.config(
        cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
        api_key=os.getenv("CLOUDINARY_API_KEY"),
        api_secret=os.getenv("CLOUDINARY_API_SECRET"),
        secure=True,
    )

    # Build a clean public_id
    safe_name = filename.rsplit(".", 1)[0].replace(" ", "_")
    public_id = f"doc-i/{submission_id}/{safe_name}"

    # Determine resource type
    if mime_type == "application/pdf":
        resource_type = "raw"
    else:
        resource_type = "image"

    # Upload as base64
    data_uri = f"data:{mime_type};base64,{base64.b64encode(file_bytes).decode()}"

    cloudinary.uploader.upload(
        data_uri,
        public_id=public_id,
        resource_type=resource_type,
        overwrite=True,
    )

    logger.info(
        f"Cloudinary upload: {public_id} " f"({len(file_bytes)} bytes, {mime_type})"
    )
    return public_id


def _cloudinary_get(public_id: str) -> bytes:
    import cloudinary.api
    import requests as req

    cloudinary.config(
        cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
        api_key=os.getenv("CLOUDINARY_API_KEY"),
        api_secret=os.getenv("CLOUDINARY_API_SECRET"),
        secure=True,
    )

    cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME")

    # Try raw first (PDFs), then image
    for resource_type in ["raw", "image"]:
        url = (
            f"https://res.cloudinary.com/{cloud_name}"
            f"/{resource_type}/upload/{public_id}"
        )
        response = req.get(url, timeout=30)
        if response.status_code == 200:
            return response.content

    raise FileNotFoundError(f"Could not retrieve file from Cloudinary: {public_id}")


def _cloudinary_delete(public_id: str) -> None:
    import cloudinary.uploader

    cloudinary.config(
        cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
        api_key=os.getenv("CLOUDINARY_API_KEY"),
        api_secret=os.getenv("CLOUDINARY_API_SECRET"),
        secure=True,
    )

    for resource_type in ["raw", "image"]:
        try:
            cloudinary.uploader.destroy(public_id, resource_type=resource_type)
        except Exception:
            pass

    logger.info(f"Cloudinary delete: {public_id}")


# ── MinIO backend ──────────────────────────────────────────────────────────
def _minio_upload(
    file_bytes: bytes,
    filename: str,
    mime_type: str,
    submission_id: str,
) -> str:
    import io
    import uuid

    from minio import Minio

    from config.settings import settings

    client = Minio(
        settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_USER,
        secret_key=settings.MINIO_PASSWORD,
        secure=settings.MINIO_SECURE,
    )

    bucket = settings.MINIO_BUCKET
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    object_key = f"{submission_id}/{uuid.uuid4().hex}.{ext}"

    client.put_object(
        bucket,
        object_key,
        io.BytesIO(file_bytes),
        length=len(file_bytes),
        content_type=mime_type,
    )

    logger.info(f"MinIO upload: {object_key} ({len(file_bytes)} bytes)")
    return object_key


def _minio_get(storage_path: str) -> bytes:

    from minio import Minio

    from config.settings import settings

    client = Minio(
        settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_USER,
        secret_key=settings.MINIO_PASSWORD,
        secure=settings.MINIO_SECURE,
    )

    response = client.get_object(settings.MINIO_BUCKET, storage_path)
    return response.read()


def _minio_delete(storage_path: str) -> None:
    from minio import Minio

    from config.settings import settings

    client = Minio(
        settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_USER,
        secret_key=settings.MINIO_PASSWORD,
        secure=settings.MINIO_SECURE,
    )

    client.remove_object(settings.MINIO_BUCKET, storage_path)
    logger.info(f"MinIO delete: {storage_path}")
