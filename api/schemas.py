"""Pydantic v2 response models — keep API JSON shape stable across refactors.

Only the response models are explicit; request bodies are minimal and inline in routes.
"""
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=False)

    account_id: str
    name: str
    official_name: Optional[str] = None
    type: str
    subtype: Optional[str] = None
    mask: Optional[str] = None
    current_balance: Optional[float] = None
    available_balance: Optional[float] = None
    limit_balance: Optional[float] = None
    iso_currency_code: Optional[str] = None
    last_balance_at: Optional[str] = None
    item_id: str
    institution_id: str
    institution_name: str
    institution_logo: Optional[str] = None
    institution_primary_color: Optional[str] = None
    last_sync_status: Optional[str] = None
    last_sync_error: Optional[str] = None
    last_sync_at: Optional[str] = None


class TransactionOut(BaseModel):
    transaction_id: str
    account_id: str
    account_name: str
    institution_name: str
    date: Optional[str] = None
    authorized_date: Optional[str] = None
    amount: float
    iso_currency_code: Optional[str] = None
    name: str
    merchant_name: Optional[str] = None
    payment_channel: Optional[str] = None
    pending: bool
    category_primary: Optional[str] = None
    category_detailed: Optional[str] = None
    category_confidence: Optional[str] = None
    removed_at: Optional[str] = None


class HoldingOut(BaseModel):
    account_id: str
    account_name: str
    security_id: str
    ticker_symbol: Optional[str] = None
    security_name: Optional[str] = None
    security_type: Optional[str] = None
    quantity: float
    institution_price: Optional[float] = None
    institution_value: Optional[float] = None
    cost_basis: Optional[float] = None
    iso_currency_code: Optional[str] = None


class NetWorthOut(BaseModel):
    total: float
    depository: float
    credit: float
    investment: float
    loan: float


class CategorySpendRow(BaseModel):
    category_primary: str
    total: float
    count: int


class LinkTokenOut(BaseModel):
    link_token: str


class ExchangeIn(BaseModel):
    public_token: str


class ExchangeOut(BaseModel):
    item_id: str


class SyncStartedOut(BaseModel):
    started: bool
    item_count: int


class SyncStatusOut(BaseModel):
    item_id: str
    institution_name: str
    last_sync_status: Optional[str] = None
    last_sync_error: Optional[str] = None
    last_sync_at: Optional[str] = None
