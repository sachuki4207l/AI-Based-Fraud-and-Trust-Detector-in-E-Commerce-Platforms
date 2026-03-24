"""test_admin.py — Admin control layer tests."""


def _setup(client):
    s = client.post("/sellers/add", json={"name": "Scammer", "account_age_days": 5}).json()
    b = client.post("/buyers/add", json={"name": "Alice"}).json()
    p = client.post("/products/add", data={
        "title": "FakeItem", "price": "5", "market_price": "100",
        "seller_id": str(s["id"]),
    }).json()
    c = client.post("/complaints/add", data={
        "buyer_id": str(b["id"]), "seller_id": str(s["id"]),
        "product_id": str(p["id"]),
        "complaint_text": "This is a scam product, completely fake",
    }).json()
    return s, b, p, c


def test_list_all_complaints(client):
    _setup(client)
    resp = client.get("/admin/complaints")
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


def test_list_pending_complaints(client):
    _setup(client)
    resp = client.get("/admin/complaints?admin_status=pending")
    assert resp.status_code == 200
    data = resp.json()
    assert all(c["admin_status"] == "pending" for c in data)


def test_approve_complaint(client):
    s, b, p, c = _setup(client)
    initial_cred = client.get(f"/buyers/{b['id']}").json()["credibility_score"]
    resp = client.put(f"/admin/complaints/{c['id']}/action", json={"action": "approve"})
    assert resp.status_code == 200
    assert resp.json()["admin_status"] == "approved"
    # Buyer credibility should increase
    after_cred = client.get(f"/buyers/{b['id']}").json()["credibility_score"]
    assert after_cred > initial_cred


def test_reject_complaint(client):
    s, b, p, c = _setup(client)
    initial_cred = client.get(f"/buyers/{b['id']}").json()["credibility_score"]
    resp = client.put(f"/admin/complaints/{c['id']}/action", json={"action": "reject"})
    assert resp.status_code == 200
    assert resp.json()["admin_status"] == "rejected"
    after_cred = client.get(f"/buyers/{b['id']}").json()["credibility_score"]
    assert after_cred <= initial_cred


def test_spam_complaint(client):
    s, b, p, c = _setup(client)
    initial_spam = client.get(f"/buyers/{b['id']}").json()["spam_flag_count"]
    resp = client.put(f"/admin/complaints/{c['id']}/action", json={"action": "spam"})
    assert resp.status_code == 200
    assert resp.json()["admin_status"] == "spam"
    after_spam = client.get(f"/buyers/{b['id']}").json()["spam_flag_count"]
    assert after_spam > initial_spam


def test_double_action_rejected(client):
    """Cannot action a complaint that was already actioned."""
    _, _, _, c = _setup(client)
    client.put(f"/admin/complaints/{c['id']}/action", json={"action": "approve"})
    resp = client.put(f"/admin/complaints/{c['id']}/action", json={"action": "reject"})
    assert resp.status_code == 400


def test_recalculate_seller(client):
    s, _, _, _ = _setup(client)
    resp = client.post(f"/admin/sellers/{s['id']}/recalculate")
    assert resp.status_code == 200
    assert "trust_score" in resp.json()


def test_suspicious_sellers(client):
    # New seller with low account age starts at 100 but may drop
    s = client.post("/sellers/add", json={"name": "Risky", "account_age_days": 3}).json()
    # Force low score via recalc
    client.post(f"/admin/sellers/{s['id']}/recalculate")
    resp = client.get("/admin/sellers/suspicious")
    assert resp.status_code == 200


def test_seller_signals(client):
    s, _, _, _ = _setup(client)
    resp = client.get(f"/admin/sellers/{s['id']}/signals")
    assert resp.status_code == 200
    data = resp.json()
    assert "signals" in data
    assert "feature_weights" in data
    assert "trust_score" in data


def test_invalid_admin_action(client):
    _, _, _, c = _setup(client)
    resp = client.put(f"/admin/complaints/{c['id']}/action", json={"action": "delete"})
    assert resp.status_code == 422


def test_complaint_not_found_admin(client):
    resp = client.put("/admin/complaints/9999/action", json={"action": "approve"})
    assert resp.status_code == 404
