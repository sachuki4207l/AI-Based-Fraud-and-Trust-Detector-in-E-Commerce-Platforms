"""test_advisory.py — Advisory engine tests with signals/explainability."""


def _seller(client, name="Shop", days=200):
    return client.post("/sellers/add", json={"name": name, "account_age_days": days}).json()

def _buyer(client, name="B"):
    return client.post("/buyers/add", json={"name": name}).json()

def _product(client, seller_id, price=100, market_price=120):
    return client.post("/products/add", data={
        "title": "Item", "price": str(price), "market_price": str(market_price),
        "seller_id": str(seller_id),
    }).json()

def _complaint(client, buyer_id, seller_id, product_id, text="Wrong item received"):
    return client.post("/complaints/add", data={
        "buyer_id": str(buyer_id), "seller_id": str(seller_id),
        "product_id": str(product_id), "complaint_text": text,
    }).json()


def test_advisory_not_found(client):
    assert client.get("/advisory/seller/9999").status_code == 404


def test_advisory_clean_seller(client):
    s = _seller(client, days=500)
    _product(client, s["id"])
    resp = client.get(f"/advisory/seller/{s['id']}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["risk_level"] == "Safe"


def test_advisory_includes_signals(client):
    """Advisory response must include the full signals block."""
    s = _seller(client)
    resp = client.get(f"/advisory/seller/{s['id']}")
    assert resp.status_code == 200
    data = resp.json()
    assert "signals" in data
    signals = data["signals"]
    required_fields = {
        "open_complaints", "total_complaints", "avg_severity",
        "mean_visual_mismatch", "buyer_credibility_weighted_sev",
        "price_anomaly_ratio", "complaint_frequency",
        "account_age_days", "has_price_anomaly", "weighted_risk",
    }
    assert required_fields.issubset(signals.keys())


def test_advisory_includes_ai_model(client):
    s = _seller(client)
    resp = client.get(f"/advisory/seller/{s['id']}")
    assert "ai_model_used" in resp.json()


def test_advisory_high_risk_new_seller(client):
    s = _seller(client, days=3)
    b = _buyer(client); p = _product(client, s["id"])
    _complaint(client, b["id"], s["id"], p["id"], text="Completely fake scam item damaged")
    resp = client.get(f"/advisory/seller/{s['id']}")
    assert resp.status_code == 200
    # New account penalty should push to Caution or High Risk
    assert resp.json()["risk_level"] in ("Caution", "High Risk")


def test_advisory_price_anomaly_safe(client):
    s = _seller(client, days=300)
    _product(client, s["id"], price=50, market_price=1000)
    _product(client, s["id"], price=30, market_price=900)
    resp = client.get(f"/advisory/seller/{s['id']}")
    data = resp.json()
    assert data["has_price_anomaly"] is True


def test_advisory_full_schema(client):
    s = _seller(client)
    resp = client.get(f"/advisory/seller/{s['id']}")
    data = resp.json()
    required = {
        "seller_id", "seller_name", "trust_score", "risk_level",
        "recommendation", "reasons", "signals", "open_complaint_count",
        "has_price_anomaly", "account_age_days", "ai_model_used",
    }
    assert required.issubset(data.keys())


def test_dual_layer_proof(client):
    """After resolving a complaint, advisory score improves."""
    s = _seller(client, days=5)
    b = _buyer(client); p = _product(client, s["id"])
    c = _complaint(client, b["id"], s["id"], p["id"], text="Scam fraud fake item")
    before = client.get(f"/advisory/seller/{s['id']}").json()["trust_score"]
    client.put("/complaints/update", json={"complaint_id": c["id"], "status": "resolved"})
    after = client.get(f"/advisory/seller/{s['id']}").json()["trust_score"]
    assert after >= before
