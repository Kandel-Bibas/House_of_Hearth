import pytest
from cryptography.exceptions import InvalidTag

from core.crypto.cipher import NONCE_SIZE, decrypt_token, encrypt_token

KEY = b"\xaa" * 32
OTHER_KEY = b"\xbb" * 32


def test_round_trip_simple():
    token = "access-sandbox-abc123-xyz"
    blob = encrypt_token(token, KEY, item_id="item_1")
    assert decrypt_token(blob, KEY, item_id="item_1") == token


def test_round_trip_unicode():
    token = "résumé 𝓐𝓑𝓒"
    blob = encrypt_token(token, KEY, item_id="item_1")
    assert decrypt_token(blob, KEY, item_id="item_1") == token


def test_round_trip_empty_string():
    blob = encrypt_token("", KEY, item_id="item_1")
    assert decrypt_token(blob, KEY, item_id="item_1") == ""


def test_aad_binding_rejects_wrong_item_id():
    blob = encrypt_token("token", KEY, item_id="item_A")
    with pytest.raises(InvalidTag):
        decrypt_token(blob, KEY, item_id="item_B")


def test_wrong_key_rejected():
    blob = encrypt_token("token", KEY, item_id="item_1")
    with pytest.raises(InvalidTag):
        decrypt_token(blob, OTHER_KEY, item_id="item_1")


def test_tampered_ciphertext_rejected():
    blob = encrypt_token("token", KEY, item_id="item_1")
    # Flip a bit in the ciphertext (after the 12-byte nonce).
    tampered = bytearray(blob)
    tampered[NONCE_SIZE] ^= 0xFF
    with pytest.raises(InvalidTag):
        decrypt_token(bytes(tampered), KEY, item_id="item_1")


def test_tampered_nonce_rejected():
    blob = encrypt_token("token", KEY, item_id="item_1")
    tampered = bytearray(blob)
    tampered[0] ^= 0xFF
    with pytest.raises(InvalidTag):
        decrypt_token(bytes(tampered), KEY, item_id="item_1")


def test_nonce_uniqueness_across_many_encryptions():
    """A reused nonce with the same key would be a catastrophic AES-GCM failure."""
    nonces = set()
    for _ in range(2000):
        blob = encrypt_token("token", KEY, item_id="item_1")
        nonces.add(blob[:NONCE_SIZE])
    assert len(nonces) == 2000


def test_layout_is_nonce_plus_ciphertext_plus_tag():
    """nonce(12) || ciphertext(N) || tag(16). Length should be 12 + N + 16."""
    plaintext = "hello"
    blob = encrypt_token(plaintext, KEY, item_id="item_1")
    assert len(blob) == NONCE_SIZE + len(plaintext.encode("utf-8")) + 16


def test_invalid_key_size_raises():
    with pytest.raises(ValueError):
        encrypt_token("token", b"\x00" * 16, item_id="item_1")  # 128-bit, we require 256
