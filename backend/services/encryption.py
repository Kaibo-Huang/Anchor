"""Encryption utilities for sensitive data like Shopify access tokens."""

from functools import lru_cache

from cryptography.fernet import Fernet

from config import get_settings


@lru_cache
def get_cipher() -> Fernet:
    """Get Fernet cipher singleton.

    The encryption key should be generated with:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    """
    settings = get_settings()
    if not settings.encryption_key:
        raise ValueError("ENCRYPTION_KEY environment variable is not set")
    return Fernet(settings.encryption_key.encode())


def encrypt(plaintext: str) -> str:
    """Encrypt sensitive data like access tokens.

    Args:
        plaintext: The string to encrypt

    Returns:
        Base64-encoded encrypted string
    """
    cipher = get_cipher()
    return cipher.encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """Decrypt sensitive data.

    Args:
        ciphertext: Base64-encoded encrypted string

    Returns:
        Decrypted plaintext string
    """
    cipher = get_cipher()
    return cipher.decrypt(ciphertext.encode()).decode()
