"""test_buyers.py — Tests for buyer CRUD endpoints."""


def test_create_buyer(client):
    resp = client.post("/buyers/add", json={"name": "Alice"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Alice"
    assert data["credibility_score"] == 100
    assert data["spam_flag_count"] == 0


def test_create_buyer_missing_name(client):
    resp = client.post("/buyers/add", json={})
    assert resp.status_code == 422


def test_get_buyer_by_id(client):
    created = client.post("/buyers/add", json={"name": "Bob"}).json()
    resp = client.get(f"/buyers/{created['id']}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Bob"


def test_get_buyer_not_found(client):
    resp = client.get("/buyers/9999")
    assert resp.status_code == 404


def test_get_all_buyers(client):
    client.post("/buyers/add", json={"name": "X"})
    client.post("/buyers/add", json={"name": "Y"})
    resp = client.get("/buyers/all")
    assert resp.status_code == 200
    assert len(resp.json()) == 2
