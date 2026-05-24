def delete_file(object_key: str) -> None:
    """Delete a file from MinIO storage."""
    from config.settings import settings

    client = _client()
    client.remove_object(settings.MINIO_BUCKET, object_key)
    logger.debug(f"Deleted file: {object_key}")
