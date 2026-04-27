"""Glue between `core.crypto` and the `Item` row.

Public API:
- store_encrypted_token(session, item_id, access_token) -> None
- load_decrypted_token(session, item_id) -> str

Both call into `core.crypto.get_or_create_master_key()` which reads from
the macOS Keychain (or the test fake_keychain fixture).
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.crypto import decrypt_token, encrypt_token, get_or_create_master_key
from core.db import Item


def store_encrypted_token(session: Session, *, item_id: str, access_token: str) -> None:
    """Encrypt `access_token` and store on the Item row identified by `item_id`.

    The Item row must already exist (Link's exchange step inserts the row first,
    THEN populates the ciphertext via this function — keeping the encryption
    logic out of the model layer). The session is NOT committed here; caller commits.
    """
    item = session.scalar(select(Item).where(Item.item_id == item_id))
    if item is None:
        raise LookupError(f"Item not found: {item_id}")
    key = get_or_create_master_key()
    item.access_token_ciphertext = encrypt_token(access_token, key, item_id=item_id)


def load_decrypted_token(session: Session, *, item_id: str) -> str:
    """Read the Item's ciphertext, decrypt, and return the plaintext access token."""
    item = session.scalar(select(Item).where(Item.item_id == item_id))
    if item is None:
        raise LookupError(f"Item not found: {item_id}")
    key = get_or_create_master_key()
    return decrypt_token(item.access_token_ciphertext, key, item_id=item_id)
