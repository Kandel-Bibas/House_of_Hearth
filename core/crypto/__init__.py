"""Crypto package — Keychain master key + AES-GCM token cipher.

Public API:
- get_or_create_master_key() -> bytes
- delete_master_key() -> None
- encrypt_token(plaintext: str, key: bytes, item_id: str) -> bytes
- decrypt_token(blob: bytes, key: bytes, item_id: str) -> str
- KeychainBackendUnavailable
"""
from core.crypto.cipher import decrypt_token, encrypt_token
from core.crypto.keychain import (
    KeychainBackendUnavailable,
    delete_master_key,
    get_or_create_master_key,
)

__all__ = [
    "KeychainBackendUnavailable",
    "decrypt_token",
    "delete_master_key",
    "encrypt_token",
    "get_or_create_master_key",
]
