"""
API Key generation and verification service.

Handles:
  - Secure key generation with doci_key_ prefix
  - SHA256 hashing for storage (never store plaintext)
  - Process access verification
"""

import hashlib
import secrets
from typing import List, Optional, Tuple

from config.logging import get_logger

logger = get_logger(__name__)


def generate_api_key() -> Tuple[str, str, str]:
    """
    Generate a new API key with secure random bytes.

    Returns:
        Tuple of (full_key, key_hash, key_prefix):
        - full_key: "doci_key_" + 32 hex chars (41 total chars)
        - key_hash: SHA256 hex digest of full_key (64 chars)
        - key_prefix: First 13 chars of full_key for identification

    Example:
        full_key:   "doci_key_a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4"
        key_hash:   "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        key_prefix: "doci_key_a1b2"
    """
    # Generate 32 random hex characters (16 bytes = 128 bits of entropy)
    random_part = secrets.token_hex(16)
    full_key = f"doci_key_{random_part}"

    key_hash = hash_api_key(full_key)
    key_prefix = full_key[:13]

    logger.debug(f"Generated new API key with prefix: {key_prefix}")

    return full_key, key_hash, key_prefix


def hash_api_key(key: str) -> str:
    """
    Hash an API key using SHA256.

    Args:
        key: The full API key string

    Returns:
        SHA256 hex digest (64 characters)
    """
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def verify_key_for_process(
    process_ids: List[str],
    target_process_id: str,
) -> bool:
    """
    Check if an API key can access a specific process.

    Args:
        process_ids: List of process IDs the key is scoped to.
                     Empty list means admin access (all processes).
        target_process_id: The process ID being accessed.

    Returns:
        True if access is allowed, False otherwise.
    """
    # Empty process_ids = admin key = access to all processes
    if not process_ids:
        return True

    return target_process_id in process_ids


def has_scope(scopes: List[str], required_scope: str) -> bool:
    """
    Check if a key has the required scope.

    Args:
        scopes: List of scopes the key has (e.g. ["read", "write"])
        required_scope: The scope required for the operation ("read" or "write")

    Returns:
        True if the key has the required scope.

    Note:
        "write" scope implies "read" access as well.
    """
    if required_scope == "read":
        # Read access if key has either "read" or "write"
        return "read" in scopes or "write" in scopes

    if required_scope == "write":
        return "write" in scopes

    # Unknown scope — deny by default
    return False


def is_admin_key(process_ids: Optional[List[str]]) -> bool:
    """
    Check if a key is an admin key (can access all processes).

    Args:
        process_ids: List of process IDs the key is scoped to.

    Returns:
        True if the key is an admin key (empty or None process_ids).
    """
    return not process_ids
