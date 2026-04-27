from datetime import date


def test_accounts_route_returns_list(client, queries_seed):
    resp = client.get("/accounts")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 3
    by_id = {a["account_id"]: a for a in body}
    assert by_id["acc_test"]["name"] == "Checking"
    assert by_id["acc_credit"]["type"] == "credit"


def test_transactions_route_default(client, queries_seed):
    resp = client.get("/transactions")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 5  # 5 non-removed
    assert body[0]["date"] >= body[-1]["date"]


def test_transactions_route_filters(client, queries_seed):
    resp = client.get(
        "/transactions",
        params={"start_date": "2026-04-01", "end_date": "2026-04-03",
                "category_primary": "FOOD_AND_DRINK", "min_amount": "40.0"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert {t["transaction_id"] for t in body} == {"txn_grocery_1"}


def test_holdings_route(client, queries_seed):
    resp = client.get("/holdings")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["ticker_symbol"] == "VTI"


def test_networth_route(client, queries_seed):
    resp = client.get("/networth")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 11250.00
    assert body["depository"] == 1000.00
    assert body["investment"] == 10000.00


def test_category_spend_route(client, queries_seed):
    resp = client.get(
        "/category-spend",
        params={"start_date": "2026-04-01", "end_date": "2026-04-30"},
    )
    assert resp.status_code == 200
    body = resp.json()
    by_cat = {row["category_primary"]: row for row in body}
    assert by_cat["FOOD_AND_DRINK"]["total"] == 164.75
    assert by_cat["FOOD_AND_DRINK"]["count"] == 3
