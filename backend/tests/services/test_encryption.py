"""
Tests for encryption service.
"""
import os
from unittest.mock import patch, MagicMock

import pytest
from cryptography.fernet import Fernet


class TestEncryption:
    """Test encryption and decryption functions."""

    @pytest.fixture(autouse=True)
    def setup_encryption_key(self):
        """Ensure test encryption key is set."""
        # Generate a valid Fernet key
        test_key = Fernet.generate_key().decode()
        with patch("services.encryption.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(encryption_key=test_key)
            # Clear the lru_cache
            from services.encryption import get_cipher
            get_cipher.cache_clear()
            yield test_key
            get_cipher.cache_clear()

    def test_encrypt_returns_string(self, setup_encryption_key):
        """Test that encrypt returns a string."""
        from services.encryption import encrypt

        with patch("services.encryption.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(encryption_key=setup_encryption_key)
            from services.encryption import get_cipher
            get_cipher.cache_clear()

            result = encrypt("test_token")
            assert isinstance(result, str)
            assert result != "test_token"

    def test_decrypt_returns_original(self, setup_encryption_key):
        """Test that decrypt returns original plaintext."""
        from services.encryption import encrypt, decrypt

        with patch("services.encryption.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(encryption_key=setup_encryption_key)
            from services.encryption import get_cipher
            get_cipher.cache_clear()

            original = "shpat_abc123_secret_token"
            encrypted = encrypt(original)
            decrypted = decrypt(encrypted)
            assert decrypted == original

    def test_encrypt_different_outputs(self, setup_encryption_key):
        """Test that same plaintext produces different ciphertext (Fernet uses random IV)."""
        from services.encryption import encrypt

        with patch("services.encryption.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(encryption_key=setup_encryption_key)
            from services.encryption import get_cipher
            get_cipher.cache_clear()

            plaintext = "same_token"
            result1 = encrypt(plaintext)
            result2 = encrypt(plaintext)
            # Fernet adds random IV, so outputs should be different
            assert result1 != result2

    def test_decrypt_tampered_ciphertext(self, setup_encryption_key):
        """Test that tampered ciphertext fails to decrypt."""
        from services.encryption import encrypt, decrypt
        from cryptography.fernet import InvalidToken

        with patch("services.encryption.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(encryption_key=setup_encryption_key)
            from services.encryption import get_cipher
            get_cipher.cache_clear()

            encrypted = encrypt("secret")
            # Tamper with the ciphertext
            tampered = encrypted[:-5] + "XXXXX"

            with pytest.raises(Exception):  # InvalidToken or similar
                decrypt(tampered)

    def test_encrypt_empty_string(self, setup_encryption_key):
        """Test encrypting empty string."""
        from services.encryption import encrypt, decrypt

        with patch("services.encryption.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(encryption_key=setup_encryption_key)
            from services.encryption import get_cipher
            get_cipher.cache_clear()

            encrypted = encrypt("")
            decrypted = decrypt(encrypted)
            assert decrypted == ""

    def test_encrypt_unicode(self, setup_encryption_key):
        """Test encrypting unicode strings."""
        from services.encryption import encrypt, decrypt

        with patch("services.encryption.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(encryption_key=setup_encryption_key)
            from services.encryption import get_cipher
            get_cipher.cache_clear()

            original = "token_with_unicode_\u4e2d\u6587"
            encrypted = encrypt(original)
            decrypted = decrypt(encrypted)
            assert decrypted == original

    def test_missing_encryption_key(self):
        """Test that missing encryption key raises error."""
        from services.encryption import get_cipher
        get_cipher.cache_clear()

        with patch("services.encryption.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(encryption_key=None)

            with pytest.raises(ValueError, match="ENCRYPTION_KEY"):
                get_cipher()
