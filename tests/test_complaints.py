"""test_complaints.py — Complaint lifecycle tests (updated for new architecture)."""

import io
from PIL import Image


def _seller(client, name="Shop", days=200):
    return client.post("/sellers/add", json={"name": name, "account_age_days": days}).json()

def _buyer(client, name="Buyer"):
    return client.post("/buyers/add", json={"name": name}).json()

def _product(client, seller_id, price=100, market_price=120):
    return client.post("/products/add", data={
        "title": "Item", "price": str(price), "market_price": str(market_price),
        "seller_id": str(seller_id),
    }).json()

def _jpeg():
    buf = io.BytesIO()
    Image.new("RGB", (50, 50), (100, 100, 100)).save(buf, format="JPEG")
    return buf.getvalue()

def _complaint(client, buyer_id, seller_id, product_id, image_bytes=None):
    """Note: no severity_level — system auto-computes it."""
    data = {
        "buyer_id":       str(buyer_id),
        "seller_id":      str(seller_id),
        "product_id":     str(product_id),
        "complaint_text": "This product looks completely different from what was listed",
    }
    files = {}
    if image_bytes:
        files = {"received_image": ("photo.jpg", image_bytes, "image/jpeg")}
    return client.post("/complaints/add", data=data, files=files or None)


def test_add_complaint_no_image(client):
    s = _seller(client)
    b = _buyer(client)
    p = _product(client, s["id"])
    resp = _complaint(client, b["id"], s["id"], p["id"])
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "open"
    assert data["admin_status"] == "pending"
    assert data["processing_status"] == "queued"
    # severity will be auto-set (may be > 0 after background task)


def test_add_complaint_no_severity_field_needed(client):
    """Confirm endpoint does NOT accept severity_level from user."""
    s = _seller(client); b = _buyer(client); p = _product(client, s["id"])
    resp = client.post("/complaints/add", data={
        "buyer_id": str(b["id"]), "seller_id": str(s["id"]),
        "product_id": str(p["id"]),
        "complaint_text": "Wrong item sent",
        "severity_level": "5",   # this should be silently ignored or cause no error
    })
    # Should still create successfully (extra field is ignored in form data)
    assert resp.status_code == 201


def test_complaint_invalid_buyer(client):
    s = _seller(client); p = _product(client, s["id"])
    resp = _complaint(client, 9999, s["id"], p["id"])
    assert resp.status_code == 404


def test_complaint_product_seller_mismatch(client):
    s1 = _seller(client, "S1"); s2 = _seller(client, "S2")
    b = _buyer(client); p = _product(client, s1["id"])
    resp = _complaint(client, b["id"], s2["id"], p["id"])
    assert resp.status_code == 400


def test_get_complaint_by_id(client):
    s = _seller(client); b = _buyer(client); p = _product(client, s["id"])
    cid = _complaint(client, b["id"], s["id"], p["id"]).json()["id"]
    resp = client.get(f"/complaints/{cid}")
    assert resp.status_code == 200


def test_update_complaint_status(client):
    s = _seller(client); b = _buyer(client); p = _product(client, s["id"])
    c = _complaint(client, b["id"], s["id"], p["id"]).json()
    resp = client.put("/complaints/update", json={"complaint_id": c["id"], "status": "resolved"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "resolved"


def test_buyer_credibility_decreases_on_complaint(client):
    s = _seller(client); b = _buyer(client); p = _product(client, s["id"])
    initial = client.get(f"/buyers/{b['id']}").json()["credibility_score"]
    _complaint(client, b["id"], s["id"], p["id"])
    after = client.get(f"/buyers/{b['id']}").json()["credibility_score"]
    assert after < initial


def test_filter_complaints_by_status(client):
    s = _seller(client)
    b1 = _buyer(client, "B1"); b2 = _buyer(client, "B2")
    p1 = _product(client, s["id"]); p2 = _product(client, s["id"])
    c1 = _complaint(client, b1["id"], s["id"], p1["id"]).json()
    _complaint(client, b2["id"], s["id"], p2["id"])
    client.put("/complaints/update", json={"complaint_id": c1["id"], "status": "resolved"})
    open_r = client.get(f"/complaints/seller/{s['id']}?status=open")
    assert len(open_r.json()) == 1
