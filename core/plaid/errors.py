"""Map Plaid `error_code` strings to sync outcomes.

Source of truth for the error → behavior table in
docs/superpowers/specs/2026-04-26-finance-tracker-design.md (section 7.2).
"""
from dataclasses import dataclass
from typing import Literal, Optional

# Codes the sync engine should retry within a single run (with backoff).
_RETRYABLE_CODES = {
    "PRODUCT_NOT_READY",
    "RATE_LIMIT_EXCEEDED",
    "INSTITUTION_DOWN",
    "INSTITUTION_NOT_RESPONDING",
}

# Codes that mean the user must re-link via Plaid Link in update mode.
_RELINK_REQUIRED_CODES = {
    "ITEM_LOGIN_REQUIRED",
    "INVALID_ACCESS_TOKEN",
    "INVALID_CREDENTIALS",
}


@dataclass(frozen=True)
class SyncOutcome:
    """Result of classifying a Plaid error.

    status: value to write into items.last_sync_status ('ok' | 'error' | 'pending').
    error: human-readable string for items.last_sync_error.
    user_action: 'relink' if the user must re-authenticate, None otherwise.
    """

    status: Literal["ok", "error", "pending"]
    error: str
    user_action: Optional[Literal["relink"]]


def classify_plaid_error(error_code: str, error_message: str) -> SyncOutcome:
    """Classify a Plaid error code → SyncOutcome.

    All non-success codes map to status='error'. The `user_action` field
    drives UI: 'relink' shows the user a Reconnect button.
    """
    user_action: Optional[Literal["relink"]] = None
    if error_code in _RELINK_REQUIRED_CODES:
        user_action = "relink"
    return SyncOutcome(
        status="error",
        error=f"{error_code}: {error_message}",
        user_action=user_action,
    )


def is_retryable(error_code: str) -> bool:
    """True if the sync engine should retry within the current run (with backoff)."""
    return error_code in _RETRYABLE_CODES
