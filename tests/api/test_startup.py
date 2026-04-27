"""Smoke test that the app boots cleanly with the startup hook skipped."""


def test_health_returns_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
