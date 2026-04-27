import base64

import pytest

from core.crypto import keychain


@pytest.fixture
def fake_keychain(monkeypatch):
    """In-memory replacement for `keyring`. Returns the backing dict."""
    store: dict[tuple[str, str], str] = {}

    def fake_get(service, account):
        return store.get((service, account))

    def fake_set(service, account, password):
        store[(service, account)] = password

    def fake_delete(service, account):
        if (service, account) not in store:
            import keyring.errors

            raise keyring.errors.PasswordDeleteError("not found")
        del store[(service, account)]

    monkeypatch.setattr(keychain.keyring, "get_password", fake_get)
    monkeypatch.setattr(keychain.keyring, "set_password", fake_set)
    monkeypatch.setattr(keychain.keyring, "delete_password", fake_delete)
    return store


def test_first_call_generates_and_stores_32_byte_key(fake_keychain):
    key = keychain.get_or_create_master_key()
    assert isinstance(key, bytes)
    assert len(key) == 32
    stored = fake_keychain[(keychain.SERVICE, keychain.ACCOUNT)]
    assert base64.b64decode(stored.encode("ascii")) == key


def test_second_call_returns_same_key(fake_keychain):
    k1 = keychain.get_or_create_master_key()
    k2 = keychain.get_or_create_master_key()
    assert k1 == k2


def test_returns_existing_key_from_keychain(fake_keychain):
    fixed = b"\x42" * 32
    fake_keychain[(keychain.SERVICE, keychain.ACCOUNT)] = base64.b64encode(fixed).decode("ascii")
    key = keychain.get_or_create_master_key()
    assert key == fixed


def test_delete_master_key_removes_entry(fake_keychain):
    keychain.get_or_create_master_key()
    assert (keychain.SERVICE, keychain.ACCOUNT) in fake_keychain
    keychain.delete_master_key()
    assert (keychain.SERVICE, keychain.ACCOUNT) not in fake_keychain


def test_delete_when_absent_is_safe(fake_keychain):
    # Should not raise
    keychain.delete_master_key()


def test_keychain_backend_unavailable_is_wrapped(monkeypatch):
    import keyring.errors

    def boom(service, account):
        raise keyring.errors.NoKeyringError("no keyring backend")

    monkeypatch.setattr(keychain.keyring, "get_password", boom)
    with pytest.raises(keychain.KeychainBackendUnavailable):
        keychain.get_or_create_master_key()
