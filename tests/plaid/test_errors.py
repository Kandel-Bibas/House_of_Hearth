import pytest

from core.plaid.errors import (
    SyncOutcome,
    classify_plaid_error,
    is_retryable,
)


def test_item_login_required_classifies_as_relink_required():
    outcome = classify_plaid_error("ITEM_LOGIN_REQUIRED", "the message")
    assert outcome.status == "error"
    assert outcome.user_action == "relink"
    assert "ITEM_LOGIN_REQUIRED" in outcome.error


def test_institution_down_classifies_as_transient():
    outcome = classify_plaid_error("INSTITUTION_DOWN", "down for maintenance")
    assert outcome.status == "error"
    assert outcome.user_action is None  # not user-actionable
    assert is_retryable("INSTITUTION_DOWN")


def test_product_not_ready_is_retryable():
    assert is_retryable("PRODUCT_NOT_READY")


def test_rate_limit_is_retryable():
    assert is_retryable("RATE_LIMIT_EXCEEDED")


def test_invalid_access_token_classifies_as_relink_required():
    outcome = classify_plaid_error("INVALID_ACCESS_TOKEN", "")
    assert outcome.user_action == "relink"


def test_unknown_code_is_classified_as_generic_error_not_retryable():
    outcome = classify_plaid_error("SOMETHING_NEW_PLAID_ADDED", "details")
    assert outcome.status == "error"
    assert "SOMETHING_NEW_PLAID_ADDED" in outcome.error
    assert outcome.user_action is None
    assert is_retryable("SOMETHING_NEW_PLAID_ADDED") is False
