def test_post_sync_returns_started_and_item_count(client, seeded_chain):
    resp = client.post("/sync")
    assert resp.status_code == 200
    body = resp.json()
    assert body["started"] is True
    assert body["item_count"] == 1


def test_post_sync_with_no_items_returns_started_false(client):
    resp = client.post("/sync")
    body = resp.json()
    assert body["started"] is False
    assert body["item_count"] == 0


def test_get_sync_status_lists_each_item(client, seeded_chain):
    resp = client.get("/sync/status")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["item_id"] == "item_test"
    assert body[0]["institution_name"] == "Test Bank"
