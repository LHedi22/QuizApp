"""Phase 0.4 DoD: the health endpoint answers 200 JSON without touching the DB."""


def test_healthz_returns_ok(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
