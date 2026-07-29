"""
Tests for the API key generation and verification service.

Covers:
- Key generation format and consistency
- SHA256 hashing
- Process access verification
- Scope checking
- Admin key detection
"""

from services.api_keys import (
    generate_api_key,
    has_scope,
    hash_api_key,
    is_admin_key,
    verify_key_for_process,
)


class TestGenerateApiKey:
    """Tests for generate_api_key()."""

    def test_returns_tuple_of_three_strings(self):
        """Should return (full_key, key_hash, key_prefix)."""
        result = generate_api_key()
        assert isinstance(result, tuple)
        assert len(result) == 3
        full_key, key_hash, key_prefix = result
        assert isinstance(full_key, str)
        assert isinstance(key_hash, str)
        assert isinstance(key_prefix, str)

    def test_full_key_has_correct_format(self):
        """Full key should be doci_key_ + 32 hex chars."""
        full_key, _, _ = generate_api_key()
        assert full_key.startswith("doci_key_")
        assert len(full_key) == 40  # "doci_key_" (8) + 32 hex chars
        # Verify the random part is hex
        random_part = full_key[8:]
        assert all(c in "0123456789abcdef" for c in random_part)

    def test_key_hash_is_64_char_hex(self):
        """Key hash should be SHA256 hex digest (64 chars)."""
        _, key_hash, _ = generate_api_key()
        assert len(key_hash) == 64
        assert all(c in "0123456789abcdef" for c in key_hash)

    def test_key_prefix_is_first_12_chars(self):
        """Key prefix should be first 12 chars of full key."""
        full_key, _, key_prefix = generate_api_key()
        assert key_prefix == full_key[:12]
        assert key_prefix.startswith("doci_key_")
        assert len(key_prefix) == 12

    def test_hash_matches_full_key(self):
        """Hashing the full key should produce the same hash."""
        full_key, key_hash, _ = generate_api_key()
        computed_hash = hash_api_key(full_key)
        assert computed_hash == key_hash

    def test_generates_unique_keys(self):
        """Each call should generate a different key."""
        keys = [generate_api_key()[0] for _ in range(10)]
        assert len(set(keys)) == 10  # All unique


class TestHashApiKey:
    """Tests for hash_api_key()."""

    def test_returns_64_char_hex(self):
        """Should return SHA256 hex digest."""
        result = hash_api_key("test_key_123")
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_consistent_hashing(self):
        """Same input should always produce same hash."""
        key = "doci_key_abcdef1234567890"
        hash1 = hash_api_key(key)
        hash2 = hash_api_key(key)
        assert hash1 == hash2

    def test_different_keys_different_hashes(self):
        """Different inputs should produce different hashes."""
        hash1 = hash_api_key("key_one")
        hash2 = hash_api_key("key_two")
        assert hash1 != hash2

    def test_known_hash_value(self):
        """Test against a known SHA256 value."""
        # SHA256 of "test" is well-known
        result = hash_api_key("test")
        expected = "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"
        assert result == expected


class TestVerifyKeyForProcess:
    """Tests for verify_key_for_process()."""

    def test_empty_process_ids_allows_all(self):
        """Empty process_ids list should allow access to any process."""
        assert verify_key_for_process([], "proc_any") is True
        assert verify_key_for_process([], "proc_abc123") is True

    def test_process_in_list_allowed(self):
        """Process in the list should be allowed."""
        process_ids = ["proc_abc", "proc_xyz"]
        assert verify_key_for_process(process_ids, "proc_abc") is True
        assert verify_key_for_process(process_ids, "proc_xyz") is True

    def test_process_not_in_list_denied(self):
        """Process not in the list should be denied."""
        process_ids = ["proc_abc", "proc_xyz"]
        assert verify_key_for_process(process_ids, "proc_other") is False
        assert verify_key_for_process(process_ids, "proc_123") is False

    def test_single_process_scope(self):
        """Key scoped to single process."""
        process_ids = ["proc_benefits"]
        assert verify_key_for_process(process_ids, "proc_benefits") is True
        assert verify_key_for_process(process_ids, "proc_mortgage") is False


class TestHasScope:
    """Tests for has_scope()."""

    def test_read_scope_allows_read(self):
        """read scope should allow read access."""
        assert has_scope(["read"], "read") is True

    def test_write_scope_allows_read(self):
        """write scope should implicitly allow read access."""
        assert has_scope(["write"], "read") is True

    def test_write_scope_allows_write(self):
        """write scope should allow write access."""
        assert has_scope(["write"], "write") is True

    def test_read_scope_denies_write(self):
        """read-only scope should deny write access."""
        assert has_scope(["read"], "write") is False

    def test_both_scopes_allow_both(self):
        """Both scopes should allow both operations."""
        scopes = ["read", "write"]
        assert has_scope(scopes, "read") is True
        assert has_scope(scopes, "write") is True

    def test_unknown_scope_denied(self):
        """Unknown scope requirements should be denied."""
        assert has_scope(["read", "write"], "admin") is False
        assert has_scope(["read"], "delete") is False


class TestIsAdminKey:
    """Tests for is_admin_key()."""

    def test_empty_list_is_admin(self):
        """Empty process_ids means admin."""
        assert is_admin_key([]) is True

    def test_none_is_admin(self):
        """None process_ids means admin."""
        assert is_admin_key(None) is True

    def test_non_empty_list_not_admin(self):
        """Non-empty process_ids is not admin."""
        assert is_admin_key(["proc_abc"]) is False
        assert is_admin_key(["proc_a", "proc_b"]) is False
