"""End-to-end: keychain → key → encrypt → store-roundtrip → decrypt."""
import pytest

from core.crypto import (
    decrypt_token,
    encrypt_token,
    get_or_create_master_key,
)
from core.crypto import keychain


@pytest.fixture
def fake_keychain(monkeypatch):
    store: dict[tuple[str, str], str] = {}
    monkeypatch.setattr(
        keychain.keyring, "get_password", lambda s, a: store.get((s, a))
    )
    monkeypatch.setattr(
        keychain.keyring, "set_password",
        lambda s, a, p: store.__setitem__((s, a), p),
    )
    return store


def test_encrypt_with_keychain_key_then_decrypt(fake_keychain):
    key = get_or_create_master_key()
    blob = encrypt_token("access-sandbox-real-token", key, item_id="item_1")

    # Simulate process restart: re-read the key from keychain.
    same_key = get_or_create_master_key()
    assert same_key == key

    assert decrypt_token(blob, same_key, item_id="item_1") == "access-sandbox-real-token"


def test_two_items_with_same_key_have_independent_ciphertexts(fake_keychain):
    key = get_or_create_master_key()
    blob_a = encrypt_token("token_A", key, item_id="item_A")
    blob_b = encrypt_token("token_B", key, item_id="item_B")

    assert blob_a != blob_b
    assert decrypt_token(blob_a, key, item_id="item_A") == "token_A"
    assert decrypt_token(blob_b, key, item_id="item_B") == "token_B"
