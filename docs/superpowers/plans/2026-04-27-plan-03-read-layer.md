# Plan 3 — Read Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `core/queries/` — pure read functions that the API (Plan 4) and MCP server (Plan 6) both consume. No Plaid calls, no writes, no HTTP. Just SELECTs over the existing schema, returning JSON-safe dicts.

**Architecture:** Five query functions, each a thin SQLAlchemy 2.x wrapper that returns plain dicts (not ORM objects). Soft-deleted transactions (`removed_at IS NOT NULL`) are excluded by default everywhere. The shared `tests/conftest.py` from Plan 2's polish provides `engine`, `session`, `seeded_chain`. Per-test seeders extend that chain with the rows each test needs.

**Tech Stack:** SQLAlchemy 2.x (sync), pytest. No new dependencies.

**Spec reference:** `docs/superpowers/specs/2026-04-26-finance-tracker-design.md` — section 5.4 (MCP query tools list), section 6 (schema).

---

## File Structure (created by this plan)

```
core/queries/
├── __init__.py           # public API
├── transactions.py       # search_transactions
├── networth.py           # net_worth
├── categories.py         # category_spend
├── holdings.py           # list_holdings
└── accounts.py           # list_accounts

tests/queries/
├── __init__.py
├── conftest.py           # extra fixture: extra_seed (txns/holdings on top of seeded_chain)
├── test_transactions.py
├── test_networth.py
├── test_categories.py
├── test_holdings.py
└── test_accounts.py
```

Public API (Task 5):
```python
from core.queries import (
    search_transactions, net_worth, category_spend, list_holdings, list_accounts,
)
```

---

## Task 1: Queries scaffold + `search_transactions`

**Files:**
- Create: `core/queries/__init__.py` (empty for now; Task 5 wires it)
- Create: `core/queries/transactions.py`
- Create: `tests/queries/__init__.py` (empty)
- Create: `tests/queries/conftest.py`
- Create: `tests/queries/test_transactions.py`

- [ ] **Step 1: Create the queries package directories**

```bash
cd /Users/bibas/personal/finance-tracker
mkdir -p core/queries tests/queries
touch core/queries/__init__.py tests/queries/__init__.py
```

- [ ] **Step 2: Create `tests/queries/conftest.py` with the seeder fixture**

Write to `tests/queries/conftest.py`:

```python
"""Per-test seeder helper for queries tests.

Builds on the shared `seeded_chain` fixture from `tests/conftest.py`
(institution → item → account) by adding investment account, securities, holdings,
and a small fixed set of transactions covering different categories and dates.
"""
from datetime import date, datetime

import pytest

from core.db import Account, Holding, Item, Security, Transaction


@pytest.fixture
def queries_seed(session, seeded_chain):
    """Extend the base seed with two more accounts (one credit, one investment),
    one security, two holdings, and 6 transactions across categories.

    Returns a dict with each created object so tests can reference them.
    """
    inst = seeded_chain["institution"]  # ins_test
    item = seeded_chain["item"]          # item_test
    base_acct = seeded_chain["account"]  # acc_test, depository checking, balance 1000.00

    credit_acct = Account(
        account_id="acc_credit",
        item_id=item.item_id,
        name="Credit Card",
        type="credit",
        subtype="credit card",
        current_balance=-250.00,        # owed
        limit_balance=5000.00,
        iso_currency_code="USD",
    )
    invest_acct = Account(
        account_id="acc_invest",
        item_id=item.item_id,
        name="Brokerage",
        type="investment",
        subtype="brokerage",
        current_balance=10000.00,
        iso_currency_code="USD",
    )
    sec = Security(
        security_id="sec_VTI",
        ticker_symbol="VTI",
        name="Vanguard Total Stock Market",
        type="etf",
        close_price=250.00,
    )
    holding = Holding(
        account_id="acc_invest",
        security_id="sec_VTI",
        quantity=40.0,
        institution_price=250.00,
        institution_value=10000.00,
    )

    txns = [
        Transaction(
            transaction_id="txn_grocery_1",
            account_id=base_acct.account_id,
            date=date(2026, 4, 1),
            amount=42.50,
            name="WHOLE FOODS",
            merchant_name="Whole Foods",
            payment_channel="in store",
            pending=False,
            category_primary="FOOD_AND_DRINK",
            category_detailed="FOOD_AND_DRINK_GROCERIES",
        ),
        Transaction(
            transaction_id="txn_grocery_2",
            account_id=base_acct.account_id,
            date=date(2026, 4, 10),
            amount=37.25,
            name="TRADER JOES",
            merchant_name="Trader Joe's",
            payment_channel="in store",
            pending=False,
            category_primary="FOOD_AND_DRINK",
            category_detailed="FOOD_AND_DRINK_GROCERIES",
        ),
        Transaction(
            transaction_id="txn_restaurant_1",
            account_id=base_acct.account_id,
            date=date(2026, 4, 5),
            amount=85.00,
            name="CHEZ PANISSE",
            merchant_name="Chez Panisse",
            payment_channel="in store",
            pending=False,
            category_primary="FOOD_AND_DRINK",
            category_detailed="FOOD_AND_DRINK_RESTAURANTS",
        ),
        Transaction(
            transaction_id="txn_gas_1",
            account_id=credit_acct.account_id,
            date=date(2026, 4, 12),
            amount=55.00,
            name="SHELL #1234",
            merchant_name="Shell",
            payment_channel="in store",
            pending=False,
            category_primary="TRANSPORTATION",
            category_detailed="TRANSPORTATION_GAS",
        ),
        Transaction(
            transaction_id="txn_paycheck",
            account_id=base_acct.account_id,
            date=date(2026, 4, 15),
            amount=-3000.00,                # negative = inflow per Plaid convention
            name="ACME CORP PAYROLL",
            merchant_name="Acme Corp",
            payment_channel="other",
            pending=False,
            category_primary="INCOME",
            category_detailed="INCOME_WAGES",
        ),
        Transaction(
            transaction_id="txn_removed",   # soft-deleted — should be excluded by default
            account_id=base_acct.account_id,
            date=date(2026, 4, 8),
            amount=20.00,
            name="OLD TXN",
            merchant_name="Old Vendor",
            payment_channel="online",
            pending=False,
            category_primary="GENERAL_MERCHANDISE",
            category_detailed="GENERAL_MERCHANDISE_OTHER",
            removed_at=datetime(2026, 4, 9),
        ),
    ]

    session.add_all([credit_acct, invest_acct, sec, holding, *txns])
    session.commit()

    return {
        "institution": inst,
        "item": item,
        "depository": base_acct,
        "credit": credit_acct,
        "investment": invest_acct,
        "security": sec,
        "holding": holding,
        "txns": txns,
    }
```

- [ ] **Step 3: Write the failing test**

Write to `tests/queries/test_transactions.py`:

```python
from datetime import date

from core.queries.transactions import search_transactions


def test_returns_all_non_removed_by_default(session, queries_seed):
    """No filters → all 5 non-removed transactions, newest first."""
    results = search_transactions(session)
    assert len(results) == 5
    # The seeded `txn_removed` (date 2026-04-08, removed_at set) is excluded.
    assert all(r["transaction_id"] != "txn_removed" for r in results)
    # Default sort: date desc.
    dates = [r["date"] for r in results]
    assert dates == sorted(dates, reverse=True)


def test_returns_dicts_not_orm_objects(session, queries_seed):
    """Result rows are JSON-safe dicts, not SQLAlchemy objects."""
    results = search_transactions(session)
    assert isinstance(results, list)
    assert isinstance(results[0], dict)
    # date should be ISO string for JSON-safety, not datetime.date.
    assert isinstance(results[0]["date"], str)


def test_filters_by_date_range(session, queries_seed):
    """Inclusive on both ends."""
    results = search_transactions(session, start_date=date(2026, 4, 5), end_date=date(2026, 4, 12))
    ids = {r["transaction_id"] for r in results}
    assert ids == {"txn_restaurant_1", "txn_grocery_2", "txn_gas_1"}


def test_filters_by_category_primary(session, queries_seed):
    results = search_transactions(session, category_primary="FOOD_AND_DRINK")
    ids = {r["transaction_id"] for r in results}
    assert ids == {"txn_grocery_1", "txn_grocery_2", "txn_restaurant_1"}


def test_filters_by_merchant_name_substring(session, queries_seed):
    """Substring match, case-insensitive."""
    results = search_transactions(session, merchant_name="whole")
    ids = {r["transaction_id"] for r in results}
    assert ids == {"txn_grocery_1"}


def test_filters_by_account_id(session, queries_seed):
    results = search_transactions(session, account_id="acc_credit")
    ids = {r["transaction_id"] for r in results}
    assert ids == {"txn_gas_1"}


def test_filters_by_min_max_amount(session, queries_seed):
    """Amount filters work over outflows; negatives (income) are below 0."""
    results = search_transactions(session, min_amount=50.0, max_amount=90.0)
    ids = {r["transaction_id"] for r in results}
    assert ids == {"txn_restaurant_1", "txn_gas_1"}


def test_include_removed_returns_soft_deleted_too(session, queries_seed):
    results = search_transactions(session, include_removed=True)
    ids = {r["transaction_id"] for r in results}
    assert "txn_removed" in ids


def test_limit_truncates_results(session, queries_seed):
    results = search_transactions(session, limit=2)
    assert len(results) == 2


def test_combined_filters(session, queries_seed):
    """Date + category + min_amount in one call. Tight date range (4/1-4/3)
    isolates txn_grocery_1 (4/1, $42.50, FOOD_AND_DRINK) from txn_restaurant_1
    (4/5, $85.00, also FOOD_AND_DRINK)."""
    results = search_transactions(
        session,
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 3),
        category_primary="FOOD_AND_DRINK",
        min_amount=40.0,
    )
    ids = {r["transaction_id"] for r in results}
    assert ids == {"txn_grocery_1"}
```

- [ ] **Step 4: Run test to confirm it fails**

```bash
.venv/bin/pytest tests/queries/test_transactions.py -v
```

Expected: ImportError on `core.queries.transactions`.

- [ ] **Step 5: Implement `core/queries/transactions.py`**

Write to `core/queries/transactions.py`:

```python
"""search_transactions — filtered, soft-delete-aware transaction list.

Returns JSON-safe dicts (date → ISO string, no SQLAlchemy objects).
"""
from datetime import date as date_t
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.db import Transaction


def _row_to_dict(t: Transaction) -> dict[str, Any]:
    return {
        "transaction_id": t.transaction_id,
        "account_id": t.account_id,
        "date": t.date.isoformat() if t.date else None,
        "authorized_date": t.authorized_date.isoformat() if t.authorized_date else None,
        "amount": t.amount,
        "iso_currency_code": t.iso_currency_code,
        "name": t.name,
        "merchant_name": t.merchant_name,
        "payment_channel": t.payment_channel,
        "pending": t.pending,
        "category_primary": t.category_primary,
        "category_detailed": t.category_detailed,
        "category_confidence": t.category_confidence,
        "removed_at": t.removed_at.isoformat() if t.removed_at else None,
    }


def search_transactions(
    session: Session,
    *,
    start_date: Optional[date_t] = None,
    end_date: Optional[date_t] = None,
    account_id: Optional[str] = None,
    category_primary: Optional[str] = None,
    category_detailed: Optional[str] = None,
    merchant_name: Optional[str] = None,        # substring, case-insensitive
    min_amount: Optional[float] = None,
    max_amount: Optional[float] = None,
    include_removed: bool = False,
    limit: Optional[int] = None,
) -> list[dict[str, Any]]:
    """Return matching transactions as JSON-safe dicts, newest first.

    Defaults: excludes soft-deleted rows (removed_at IS NULL). Pass
    `include_removed=True` to include them.
    """
    stmt = select(Transaction)

    if not include_removed:
        stmt = stmt.where(Transaction.removed_at.is_(None))
    if start_date is not None:
        stmt = stmt.where(Transaction.date >= start_date)
    if end_date is not None:
        stmt = stmt.where(Transaction.date <= end_date)
    if account_id is not None:
        stmt = stmt.where(Transaction.account_id == account_id)
    if category_primary is not None:
        stmt = stmt.where(Transaction.category_primary == category_primary)
    if category_detailed is not None:
        stmt = stmt.where(Transaction.category_detailed == category_detailed)
    if merchant_name is not None:
        # SQLite LIKE is case-insensitive for ASCII by default.
        stmt = stmt.where(Transaction.merchant_name.ilike(f"%{merchant_name}%"))
    if min_amount is not None:
        stmt = stmt.where(Transaction.amount >= min_amount)
    if max_amount is not None:
        stmt = stmt.where(Transaction.amount <= max_amount)

    stmt = stmt.order_by(Transaction.date.desc(), Transaction.transaction_id.desc())
    if limit is not None:
        stmt = stmt.limit(limit)

    rows = session.scalars(stmt).all()
    return [_row_to_dict(t) for t in rows]
```

- [ ] **Step 6: Run tests**

```bash
.venv/bin/pytest tests/queries/test_transactions.py -v
```

Expected: 10 passed.

- [ ] **Step 7: Commit**

```bash
git add core/queries/__init__.py core/queries/transactions.py \
        tests/queries/__init__.py tests/queries/conftest.py tests/queries/test_transactions.py
git commit -m "feat(queries): search_transactions with filters + soft-delete (Plan 3, Task 1)"
```

---

## Task 2: `net_worth` + `category_spend`

**Files:**
- Create: `core/queries/networth.py`
- Create: `core/queries/categories.py`
- Create: `tests/queries/test_networth.py`
- Create: `tests/queries/test_categories.py`

- [ ] **Step 1: Write failing tests for net_worth**

Write to `tests/queries/test_networth.py`:

```python
from core.queries.networth import net_worth


def test_net_worth_sums_balances_with_correct_signs(session, queries_seed):
    """
    Seed has:
      - depository (acc_test): +1000.00
      - credit (acc_credit): -250.00 (current_balance is what's owed; subtract from net worth)
      - investment (acc_invest): +10000.00
    Expected: 1000 + 10000 - abs(-250)... wait, actually credit balance is signed:
      Plaid reports credit accounts with positive current_balance = amount owed.
      So net worth subtracts credit balances and adds depository + investment.
      Our seed puts credit current_balance at -250.00 (refund / overpayment).
      Following the rule "credit reduces net worth", net = 1000 + 10000 - (-250) = 11250?
      No — for nuance: a negative current_balance on a credit card means the bank owes YOU
      (you overpaid). So that should ADD to net worth.

    Convention used here:
      net_worth = sum(depository + investment) - sum(credit + loan)
      where balance values for credit/loan are taken as Plaid reports them
      (positive = owed). A negative credit balance flips the sign correctly.

    With seed values:
      depository: +1000.00
      investment: +10000.00
      credit:     -250.00 (we owe -250, i.e., bank owes us 250 → net worth +250)

    Expected: 1000 + 10000 - (-250) = 11250.00.
    """
    result = net_worth(session)
    assert result["total"] == 11250.00
    assert result["depository"] == 1000.00
    assert result["credit"] == -250.00       # raw sum from Plaid convention
    assert result["investment"] == 10000.00
    assert result["loan"] == 0.0


def test_net_worth_with_no_accounts(session):
    """Empty DB → all zeros."""
    result = net_worth(session)
    assert result["total"] == 0.0
    assert result["depository"] == 0.0
    assert result["credit"] == 0.0
    assert result["investment"] == 0.0
    assert result["loan"] == 0.0


def test_net_worth_includes_only_accounts_with_balance(session, queries_seed):
    """Account with NULL current_balance is treated as 0.0 — doesn't crash, doesn't skew."""
    from core.db import Account, Item

    null_balance = Account(
        account_id="acc_unknown",
        item_id="item_test",
        name="Unknown",
        type="depository",
        subtype="checking",
        current_balance=None,
    )
    session.add(null_balance)
    session.commit()

    result = net_worth(session)
    # Same as before — null treated as 0.
    assert result["total"] == 11250.00
```

- [ ] **Step 2: Implement `core/queries/networth.py`**

Write to `core/queries/networth.py`:

```python
"""net_worth — sum of account balances, signed by account type.

Returns:
    {
        "total": float,
        "depository": float,
        "credit": float,         # raw sum (Plaid convention: positive = owed)
        "investment": float,
        "loan": float,
    }

Sign convention for `total`:
    total = depository + investment - credit - loan
"""
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.db import Account


def net_worth(session: Session) -> dict[str, Any]:
    """Compute net worth across all accounts."""
    stmt = (
        select(Account.type, func.coalesce(func.sum(Account.current_balance), 0.0))
        .group_by(Account.type)
    )
    by_type = {row[0]: float(row[1]) for row in session.execute(stmt).all()}

    depository = by_type.get("depository", 0.0)
    credit = by_type.get("credit", 0.0)
    investment = by_type.get("investment", 0.0)
    loan = by_type.get("loan", 0.0)

    return {
        "total": depository + investment - credit - loan,
        "depository": depository,
        "credit": credit,
        "investment": investment,
        "loan": loan,
    }
```

- [ ] **Step 3: Run net_worth tests**

```bash
.venv/bin/pytest tests/queries/test_networth.py -v
```

Expected: 3 passed.

- [ ] **Step 4: Write failing tests for category_spend**

Write to `tests/queries/test_categories.py`:

```python
from datetime import date

from core.queries.categories import category_spend


def test_category_spend_groups_by_primary_category(session, queries_seed):
    """In the seeded date range, FOOD_AND_DRINK has 3 txns summing to 164.75
    (42.50 + 37.25 + 85.00); TRANSPORTATION has 1 (55.00); INCOME has -3000.
    Income is excluded from spend by default (positive amounts only)."""
    result = category_spend(session, start_date=date(2026, 4, 1), end_date=date(2026, 4, 30))
    by_cat = {row["category_primary"]: row["total"] for row in result}
    assert by_cat["FOOD_AND_DRINK"] == 42.50 + 37.25 + 85.00
    assert by_cat["TRANSPORTATION"] == 55.00
    # INCOME excluded (negative amounts skipped).
    assert "INCOME" not in by_cat


def test_category_spend_excludes_removed_rows(session, queries_seed):
    """txn_removed (GENERAL_MERCHANDISE, removed_at set) should not appear."""
    result = category_spend(session, start_date=date(2026, 4, 1), end_date=date(2026, 4, 30))
    cats = {row["category_primary"] for row in result}
    assert "GENERAL_MERCHANDISE" not in cats


def test_category_spend_returns_count_per_category(session, queries_seed):
    result = category_spend(session, start_date=date(2026, 4, 1), end_date=date(2026, 4, 30))
    by_cat_count = {row["category_primary"]: row["count"] for row in result}
    assert by_cat_count["FOOD_AND_DRINK"] == 3
    assert by_cat_count["TRANSPORTATION"] == 1


def test_category_spend_empty_range(session, queries_seed):
    """Date range with no transactions — empty list."""
    result = category_spend(session, start_date=date(2099, 1, 1), end_date=date(2099, 12, 31))
    assert result == []


def test_category_spend_sorted_by_total_desc(session, queries_seed):
    """Highest spend first."""
    result = category_spend(session, start_date=date(2026, 4, 1), end_date=date(2026, 4, 30))
    totals = [row["total"] for row in result]
    assert totals == sorted(totals, reverse=True)
```

- [ ] **Step 5: Implement `core/queries/categories.py`**

Write to `core/queries/categories.py`:

```python
"""category_spend — outflow grouped by personal_finance_category.primary.

Excludes inflows (negative amounts, per Plaid convention) and soft-deleted txns.
"""
from datetime import date as date_t
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from core.db import Transaction


def category_spend(
    session: Session,
    *,
    start_date: date_t,
    end_date: date_t,
) -> list[dict[str, Any]]:
    """Sum outflows by category over [start_date, end_date] inclusive.

    Returns: list of {"category_primary": str, "total": float, "count": int},
    sorted by total descending. Inflows (amount < 0) and soft-deleted rows are excluded.
    Categories with NULL primary are aggregated under "UNCATEGORIZED".
    """
    cat_expr = func.coalesce(Transaction.category_primary, "UNCATEGORIZED")
    stmt = (
        select(
            cat_expr.label("category_primary"),
            func.sum(Transaction.amount).label("total"),
            func.count(Transaction.transaction_id).label("count"),
        )
        .where(Transaction.removed_at.is_(None))
        .where(Transaction.date >= start_date)
        .where(Transaction.date <= end_date)
        .where(Transaction.amount > 0)
        .group_by(cat_expr)
        .order_by(func.sum(Transaction.amount).desc())
    )
    rows = session.execute(stmt).all()
    return [
        {"category_primary": r.category_primary, "total": float(r.total), "count": int(r.count)}
        for r in rows
    ]
```

- [ ] **Step 6: Run category_spend tests**

```bash
.venv/bin/pytest tests/queries/test_categories.py -v
```

Expected: 5 passed.

- [ ] **Step 7: Run the full suite**

```bash
.venv/bin/pytest -v
```

Expected: 68 prior + 10 (Task 1) + 3 + 5 = 86 passed (+ 1 skipped).

- [ ] **Step 8: Commit**

```bash
git add core/queries/networth.py core/queries/categories.py \
        tests/queries/test_networth.py tests/queries/test_categories.py
git commit -m "feat(queries): net_worth + category_spend (Plan 3, Task 2)"
```

---

## Task 3: `list_holdings` + `list_accounts`

**Files:**
- Create: `core/queries/holdings.py`
- Create: `core/queries/accounts.py`
- Create: `tests/queries/test_holdings.py`
- Create: `tests/queries/test_accounts.py`

- [ ] **Step 1: Write failing tests for list_holdings**

Write to `tests/queries/test_holdings.py`:

```python
from core.queries.holdings import list_holdings


def test_list_holdings_joins_securities(session, queries_seed):
    """Each holding row gets ticker_symbol + security name from the joined Security row."""
    rows = list_holdings(session)
    assert len(rows) == 1
    h = rows[0]
    assert h["account_id"] == "acc_invest"
    assert h["security_id"] == "sec_VTI"
    assert h["ticker_symbol"] == "VTI"
    assert h["security_name"] == "Vanguard Total Stock Market"
    assert h["quantity"] == 40.0
    assert h["institution_value"] == 10000.00
    assert h["security_type"] == "etf"


def test_list_holdings_empty_when_no_holdings(session, seeded_chain):
    """seeded_chain has no holdings; list_holdings returns []."""
    assert list_holdings(session) == []


def test_list_holdings_includes_account_name(session, queries_seed):
    """Each row includes the human-readable account name (not just the id)."""
    rows = list_holdings(session)
    assert rows[0]["account_name"] == "Brokerage"
```

- [ ] **Step 2: Implement `core/queries/holdings.py`**

Write to `core/queries/holdings.py`:

```python
"""list_holdings — current investment positions joined with security + account metadata."""
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.db import Account, Holding, Security


def list_holdings(session: Session) -> list[dict[str, Any]]:
    """Return current holdings, joined with security and account metadata."""
    stmt = (
        select(Holding, Security, Account)
        .join(Security, Security.security_id == Holding.security_id)
        .join(Account, Account.account_id == Holding.account_id)
        .order_by(Account.account_id, Security.ticker_symbol)
    )
    rows = session.execute(stmt).all()
    return [
        {
            "account_id": h.account_id,
            "account_name": a.name,
            "security_id": h.security_id,
            "ticker_symbol": s.ticker_symbol,
            "security_name": s.name,
            "security_type": s.type,
            "quantity": h.quantity,
            "institution_price": h.institution_price,
            "institution_value": h.institution_value,
            "cost_basis": h.cost_basis,
            "iso_currency_code": s.iso_currency_code,
        }
        for h, s, a in rows
    ]
```

- [ ] **Step 3: Run holdings tests**

```bash
.venv/bin/pytest tests/queries/test_holdings.py -v
```

Expected: 3 passed.

- [ ] **Step 4: Write failing tests for list_accounts**

Write to `tests/queries/test_accounts.py`:

```python
from core.queries.accounts import list_accounts


def test_list_accounts_returns_all_with_institution_metadata(session, queries_seed):
    rows = list_accounts(session)
    # 3 accounts in seed: acc_test, acc_credit, acc_invest
    assert len(rows) == 3
    by_id = {r["account_id"]: r for r in rows}
    assert by_id["acc_test"]["institution_name"] == "Test Bank"
    assert by_id["acc_test"]["type"] == "depository"
    assert by_id["acc_credit"]["type"] == "credit"
    assert by_id["acc_invest"]["type"] == "investment"


def test_list_accounts_includes_last_sync_status(session, queries_seed):
    """Item.last_sync_status / last_sync_error / last_sync_at are exposed per account."""
    from core.db import Item
    item = session.get(Item, "item_test")
    item.last_sync_status = "ok"
    session.commit()

    rows = list_accounts(session)
    for r in rows:
        assert r["last_sync_status"] == "ok"
        assert r["last_sync_error"] is None


def test_list_accounts_balances_present(session, queries_seed):
    rows = list_accounts(session)
    by_id = {r["account_id"]: r for r in rows}
    assert by_id["acc_test"]["current_balance"] == 1000.00
    assert by_id["acc_credit"]["limit_balance"] == 5000.00


def test_list_accounts_empty(session):
    """Empty DB → empty list."""
    assert list_accounts(session) == []
```

- [ ] **Step 5: Implement `core/queries/accounts.py`**

Write to `core/queries/accounts.py`:

```python
"""list_accounts — accounts joined with their Item and Institution for UI display."""
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.db import Account, Institution, Item


def list_accounts(session: Session) -> list[dict[str, Any]]:
    """Return all accounts with institution name and last-sync status from their Item."""
    stmt = (
        select(Account, Item, Institution)
        .join(Item, Item.item_id == Account.item_id)
        .join(Institution, Institution.institution_id == Item.institution_id)
        .order_by(Institution.name, Account.name)
    )
    rows = session.execute(stmt).all()
    return [
        {
            "account_id": a.account_id,
            "name": a.name,
            "official_name": a.official_name,
            "type": a.type,
            "subtype": a.subtype,
            "mask": a.mask,
            "current_balance": a.current_balance,
            "available_balance": a.available_balance,
            "limit_balance": a.limit_balance,
            "iso_currency_code": a.iso_currency_code,
            "last_balance_at": a.last_balance_at.isoformat() if a.last_balance_at else None,
            "item_id": i.item_id,
            "institution_id": inst.institution_id,
            "institution_name": inst.name,
            "institution_logo": inst.logo,
            "institution_primary_color": inst.primary_color,
            "last_sync_status": i.last_sync_status,
            "last_sync_error": i.last_sync_error,
            "last_sync_at": i.last_sync_at.isoformat() if i.last_sync_at else None,
        }
        for a, i, inst in rows
    ]
```

- [ ] **Step 6: Run accounts tests**

```bash
.venv/bin/pytest tests/queries/test_accounts.py -v
```

Expected: 4 passed.

- [ ] **Step 7: Commit**

```bash
git add core/queries/holdings.py core/queries/accounts.py \
        tests/queries/test_holdings.py tests/queries/test_accounts.py
git commit -m "feat(queries): list_holdings + list_accounts (Plan 3, Task 3)"
```

---

## Task 4: Queries package public API

**Files:**
- Modify: `core/queries/__init__.py`

- [ ] **Step 1: Replace `core/queries/__init__.py`**

Write to `core/queries/__init__.py`:

```python
"""Read-side query functions used by both api/ and mcp/.

Public API:
- search_transactions
- net_worth
- category_spend
- list_holdings
- list_accounts

All functions take a SQLAlchemy `Session` as the first positional arg, return
JSON-safe dicts (or lists thereof), and never write to the database.
"""
from core.queries.accounts import list_accounts
from core.queries.categories import category_spend
from core.queries.holdings import list_holdings
from core.queries.networth import net_worth
from core.queries.transactions import search_transactions

__all__ = [
    "category_spend",
    "list_accounts",
    "list_holdings",
    "net_worth",
    "search_transactions",
]
```

- [ ] **Step 2: Run the full suite**

```bash
.venv/bin/pytest -v
```

Expected: 86 passed + 1 skipped (68 prior + 10 + 3 + 5 + 3 + 4 = 93 — wait, let me recount).

Actually: 68 prior (Plan 2 close) + Task 1 (10) + Task 2 (3 + 5 = 8) + Task 3 (3 + 4 = 7) = 68 + 10 + 8 + 7 = 93 tests + 1 skipped.

- [ ] **Step 3: Commit**

```bash
git add core/queries/__init__.py
git commit -m "feat(queries): package public API exports (Plan 3, Task 4)"
```

---

## Plan 3 Verification

```bash
.venv/bin/pytest --cov=core --cov-report=term-missing -q
```

Expected:
- 93 passed + 1 skipped.
- `core/queries/*` at 100% coverage.
- 4 new commits on top of Plan 2 (+ 1 docs commit for the plan doc itself = 5 commits).

---

## Hand-off to Plan 4

Plan 4 (API + launcher) will:
- Add `api/` package with FastAPI app + routes wrapping every `core.queries.*` function.
- Add `/plaid/link-token` and `/plaid/exchange` routes wrapping `core.plaid.link.*`.
- Add `/sync` and `/sync/status` routes wrapping `core.plaid.orchestrator.*`.
- Wire startup hook: Alembic upgrade + Keychain key load + auto-sync via `core.plaid.orchestrator.sync_all_items` in a background thread.
- Add `make dev` script + `~/Desktop/Finance Tracker.command` launcher.
