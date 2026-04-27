"""AES-GCM cipher for Plaid access tokens.

On-disk format: nonce(12B) || ciphertext(N) || tag(16B), all in one BLOB.
The `item_id` is bound as additional authenticated data (AAD), so a
ciphertext copied from one row to another fails authentication.
"""
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

NONCE_SIZE = 12  # AES-GCM standard
KEY_SIZE = 32  # AES-256


def encrypt_token(plaintext: str, key: bytes, item_id: str) -> bytes:
    """Encrypt `plaintext` under `key`, binding to `item_id` as AAD.

    Returns: nonce(12) || ciphertext || tag(16). Total len = 28 + len(plaintext UTF-8).
    """
    if len(key) != KEY_SIZE:
        raise ValueError(f"key must be {KEY_SIZE} bytes (got {len(key)})")
    aesgcm = AESGCM(key)
    nonce = os.urandom(NONCE_SIZE)
    ct_and_tag = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), item_id.encode("utf-8"))
    return nonce + ct_and_tag


def decrypt_token(blob: bytes, key: bytes, item_id: str) -> str:
    """Decrypt a blob produced by `encrypt_token`.

    Raises: cryptography.exceptions.InvalidTag if the key, ciphertext, nonce,
    or item_id (AAD) does not match what was encrypted.
    """
    if len(key) != KEY_SIZE:
        raise ValueError(f"key must be {KEY_SIZE} bytes (got {len(key)})")
    nonce, ct_and_tag = blob[:NONCE_SIZE], blob[NONCE_SIZE:]
    aesgcm = AESGCM(key)
    plaintext = aesgcm.decrypt(nonce, ct_and_tag, item_id.encode("utf-8"))
    return plaintext.decode("utf-8")
