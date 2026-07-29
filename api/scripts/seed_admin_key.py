#!/usr/bin/env python3
"""
Seed script for creating an initial admin API key.

This script creates one admin API key (empty process_ids = access to all processes)
if no API keys exist in the database. The full key is printed once — save it securely.

Usage:
    python scripts/seed_admin_key.py
    make seed-admin-key

The script is idempotent — it won't create duplicate keys if one already exists.
"""

import sys
from pathlib import Path

# Add the api directory to the path so we can import our modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from db.models import ApiKey  # noqa: E402
from db.session import SessionLocal  # noqa: E402
from services.api_keys import generate_api_key  # noqa: E402


def seed_admin_key() -> None:
    """
    Create an admin API key if none exists.

    The admin key has:
    - Empty process_ids (access to all processes)
    - Full scopes (read + write)
    - No expiry

    The full key is shown ONCE at creation — save it immediately.
    """
    db = SessionLocal()
    try:
        # Check if any API keys exist
        existing = db.query(ApiKey).first()
        if existing:
            print("\n" + "=" * 60)
            print("API keys already exist in the database.")
            print(f"Found: {existing.name} ({existing.key_prefix}...)")
            print("No new key created.")
            print("=" * 60 + "\n")
            return

        # Generate the admin key
        full_key, key_hash, key_prefix = generate_api_key()

        # Create the admin key record
        admin_key = ApiKey(
            name="Admin Key - Initial Setup",
            key_prefix=key_prefix,
            key_hash=key_hash,
            process_ids=[],  # Empty = admin access to all processes
            scopes=["read", "write"],
            is_active=True,
        )
        db.add(admin_key)
        db.commit()
        db.refresh(admin_key)

        print("\n" + "=" * 60)
        print("ADMIN API KEY CREATED SUCCESSFULLY")
        print("=" * 60)
        print()
        print("Key ID:     ", admin_key.id)
        print("Name:       ", admin_key.name)
        print("Key Prefix: ", key_prefix)
        print()
        print("FULL API KEY (SAVE THIS NOW - IT WILL NOT BE SHOWN AGAIN):")
        print()
        print(f"    {full_key}")
        print()
        print("This is an ADMIN key with access to ALL processes.")
        print("Use it for admin operations and to create scoped keys.")
        print("=" * 60 + "\n")

    finally:
        db.close()


if __name__ == "__main__":
    seed_admin_key()
