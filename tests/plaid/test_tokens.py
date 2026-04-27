import pytest
from sqlalchemy import select

from core.crypto import get_or_create_master_key
from core.db import Item
from core.plaid.tokens import load_decrypted_token, store_encrypted_token


def test_store_then_load_round_trip(session, seeded_chain, fake_keychain):
    """store_encrypted_token writes encrypted bytes; load_decrypted_token returns plaintext."""
    item = seeded_chain["item"]
    store_encrypted_token(session, item_id=item.item_id, access_token="access-sandbox-xyz")
    session.commit()

    plaintext = load_decrypted_token(session, item_id=item.item_id)
    assert plaintext == "access-sandbox-xyz"


def test_store_replaces_previous_ciphertext(session, seeded_chain, fake_keychain):
    """A second store call for the same item_id overwrites the first ciphertext."""
    item = seeded_chain["item"]
    store_encrypted_token(session, item_id=item.item_id, access_token="first")
    session.commit()
    store_encrypted_token(session, item_id=item.item_id, access_token="second")
    session.commit()

    assert load_decrypted_token(session, item_id=item.item_id) == "second"


def test_load_for_unknown_item_raises(session, fake_keychain):
    with pytest.raises(LookupError):
        load_decrypted_token(session, item_id="item_does_not_exist")


def test_ciphertext_is_actually_encrypted(session, seeded_chain, fake_keychain):
    """The ciphertext column should not contain the plaintext."""
    item = seeded_chain["item"]
    store_encrypted_token(session, item_id=item.item_id, access_token="access-sandbox-xyz")
    session.commit()

    fetched = session.scalar(select(Item).where(Item.item_id == item.item_id))
    assert b"access-sandbox-xyz" not in fetched.access_token_ciphertext
    assert len(fetched.access_token_ciphertext) >= 12 + 16  # nonce + tag minimum


def test_aad_binding_to_item_id(session, seeded_chain, fake_keychain):
    """A ciphertext stored for one item_id cannot be decrypted under another."""
    item = seeded_chain["item"]
    store_encrypted_token(session, item_id=item.item_id, access_token="real-token")
    session.commit()

    # Manually copy the ciphertext to a new item with a different id.
    other_item = Item(
        item_id="item_other",
        institution_id="ins_test",
        access_token_ciphertext=item.access_token_ciphertext,
    )
    session.add(other_item)
    session.commit()

    from cryptography.exceptions import InvalidTag

    with pytest.raises(InvalidTag):
        load_decrypted_token(session, item_id="item_other")
