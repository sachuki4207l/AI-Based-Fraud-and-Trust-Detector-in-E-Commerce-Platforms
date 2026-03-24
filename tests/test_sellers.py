"""test_sellers.py — Tests for seller CRUD endpoints."""


def test_create_seller(client):
    resp = client.post("/sellers/add", json={"name": "ShopA", "account_age_days": 100})
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "ShopA"
    assert data["account_age_days"] == 100
    assert data["trust_score"] == 100
    assert "id" in data


def test_create_seller_defaults(client):
    """account_age_days should default to 0."""
    resp = client.post("/sellers/add", json={"name": "NewShop"})
    assert resp.status_code == 201
    assert resp.json()["account_age_days"] == 0


def test_create_seller_missing_name(client):
    resp = client.post("/sellers/add", json={"account_age_days": 10})
    assert resp.status_code == 422


def test_get_all_sellers_empty(client):
    resp = client.get("/sellers/all")
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_all_sellers(client):
    client.post("/sellers/add", json={"name": "A"})
    client.post("/sellers/add", json={"name": "B"})
    resp = client.get("/sellers/all")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_get_seller_by_id(client):
    created = client.post("/sellers/add", json={"name": "Solo"}).json()
    resp = client.get(f"/sellers/{created['id']}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Solo"


def test_get_seller_not_found(client):
    resp = client.get("/sellers/9999")
    assert resp.status_code == 404


def test_pagination(client):
    for i in range(5):
        client.post("/sellers/add", json={"name": f"Seller{i}"})
    resp = client.get("/sellers/all?skip=2&limit=2")
    assert resp.status_code == 200
    assert len(resp.json()) == 2
