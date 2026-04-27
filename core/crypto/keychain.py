"""macOS Keychain wrapper for the app's master encryption key.

The key is 32 random bytes, generated on first access and stored as
base64 under service `finance-tracker`, account `master-key`.
"""
import base64
import os

import keyring
import keyring.errors

SERVICE = "finance-tracker"
ACCOUNT = "master-key"
KEY_BYTES = 32


class KeychainBackendUnavailable(RuntimeError):
    """Raised when the keyring backend cannot be reached at all."""


def get_or_create_master_key() -> bytes:
    """Return the 32-byte master key.

    On first ever call: generates `os.urandom(32)`, stores it base64-encoded
    in Keychain, and returns the raw bytes.

    On subsequent calls: reads the base64 entry from Keychain and decodes it.
    macOS will prompt the user once with "Always Allow"; subsequent reads from
    the same Python binary are silent.
    """
    try:
        encoded = keyring.get_password(SERVICE, ACCOUNT)
    except keyring.errors.KeyringError as exc:
        raise KeychainBackendUnavailable(str(exc)) from exc

    if encoded is None:
        key = os.urandom(KEY_BYTES)
        try:
            keyring.set_password(SERVICE, ACCOUNT, base64.b64encode(key).decode("ascii"))
        except keyring.errors.KeyringError as exc:
            raise KeychainBackendUnavailable(str(exc)) from exc
        return key

    return base64.b64decode(encoded.encode("ascii"))


def delete_master_key() -> None:
    """Remove the master key from Keychain. Safe to call when absent."""
    try:
        keyring.delete_password(SERVICE, ACCOUNT)
    except keyring.errors.PasswordDeleteError:
        # Already absent — nothing to do.
        pass
    except keyring.errors.KeyringError as exc:
        raise KeychainBackendUnavailable(str(exc)) from exc
