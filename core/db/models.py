from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    JSON,
    LargeBinary,
    PrimaryKeyConstraint,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utcnow() -> datetime:
    """Naive-UTC timestamp. SQLite stores DateTime as ISO without tz info,
    so we strip the tzinfo after computing the UTC instant. Kept naive for
    consistent comparisons across the codebase."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class Institution(Base):
    __tablename__ = "institutions"

    institution_id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    logo: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    primary_color: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    url: Mapped[Optional[str]] = mapped_column(String, nullable=True)


class Item(Base):
    __tablename__ = "items"

    item_id: Mapped[str] = mapped_column(String, primary_key=True)
    institution_id: Mapped[str] = mapped_column(
        ForeignKey("institutions.institution_id"), nullable=False
    )
    institution: Mapped["Institution"] = relationship()
    access_token_ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    transactions_cursor: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_sync_status: Mapped[Optional[str]] = mapped_column(
        String, nullable=True  # 'ok' | 'error' | 'pending'
    )
    last_sync_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)


class Account(Base):
    __tablename__ = "accounts"

    account_id: Mapped[str] = mapped_column(String, primary_key=True)
    item_id: Mapped[str] = mapped_column(ForeignKey("items.item_id"), nullable=False)
    item: Mapped["Item"] = relationship()
    name: Mapped[str] = mapped_column(String, nullable=False)
    official_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    type: Mapped[str] = mapped_column(String, nullable=False)  # depository | credit | investment | loan
    subtype: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    mask: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    current_balance: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    available_balance: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    limit_balance: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    iso_currency_code: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    last_balance_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    raw_payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    __table_args__ = (Index("ix_accounts_item_id", "item_id"),)


class Transaction(Base):
    __tablename__ = "transactions"

    transaction_id: Mapped[str] = mapped_column(String, primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.account_id"), nullable=False)
    account: Mapped["Account"] = relationship()
    date: Mapped[date] = mapped_column(Date, nullable=False)
    authorized_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    amount: Mapped[float] = mapped_column(Float, nullable=False)  # + outflow, - inflow (Plaid convention)
    iso_currency_code: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    merchant_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    payment_channel: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    pending: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    category_primary: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    category_detailed: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    category_confidence: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    raw_payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    removed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow, nullable=False
    )

    __table_args__ = (
        Index("ix_transactions_account_date", "account_id", "date"),
        Index("ix_transactions_date", "date"),
        Index("ix_transactions_category_date", "category_primary", "date"),
        Index("ix_transactions_merchant", "merchant_name"),
        Index("ix_transactions_removed", "removed_at"),
    )


class Security(Base):
    __tablename__ = "securities"

    security_id: Mapped[str] = mapped_column(String, primary_key=True)
    ticker_symbol: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    iso_currency_code: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    close_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    close_price_as_of: Mapped[Optional[date]] = mapped_column(Date, nullable=True)


class Holding(Base):
    __tablename__ = "holdings"

    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.account_id"), nullable=False)
    account: Mapped["Account"] = relationship()
    security_id: Mapped[str] = mapped_column(ForeignKey("securities.security_id"), nullable=False)
    security: Mapped["Security"] = relationship()
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    institution_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    institution_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cost_basis: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    last_synced_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)

    __table_args__ = (PrimaryKeyConstraint("account_id", "security_id"),)
