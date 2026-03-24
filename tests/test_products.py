"""test_products.py — Tests for product CRUD endpoints."""

import io
from PIL import Image


def _make_jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (50, 50), (100, 100, 100)).save(buf, format="JPEG")
    return buf.getvalue()


def _add_seller(client, name="ShopX", days=200):
    return client.post("/sellers/add", json={"name": name, "account_age_days": days}).json()


def test_add_product_no_image(client):
    seller = _add_seller(client)
    resp = client.post("/products/add", data={
        "title": "Widget",
        "price": "19.99",
        "market_price": "29.99",
        "seller_id": str(seller["id"]),
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "Widget"
    assert data["price"] == 19.99
    assert data["market_price"] == 29.99


def test_add_product_with_image(client):
    seller = _add_seller(client)
    resp = client.post("/products/add",
        data={
            "title": "Gadget",
            "price": "9.99",
            "market_price": "15.00",
            "seller_id": str(seller["id"]),
        },
        files={"image": ("test.jpg", _make_jpeg(), "image/jpeg")},
    )
    assert resp.status_code == 201
    assert resp.json()["image_path"].startswith("uploads/products/")


def test_add_product_invalid_seller(client):
    resp = client.post("/products/add", data={
        "title": "Ghost",
        "price": "5.00",
        "market_price": "10.00",
        "seller_id": "9999",
    })
    assert resp.status_code == 404


def test_add_product_negative_price(client):
    seller = _add_seller(client)
    resp = client.post("/products/add", data={
        "title": "BadPrice",
        "price": "-5",
        "market_price": "10",
        "seller_id": str(seller["id"]),
    })
    assert resp.status_code == 422


def test_get_product_by_id(client):
    seller = _add_seller(client)
    created = client.post("/products/add", data={
        "title": "Solo",
        "price": "10",
        "market_price": "20",
        "seller_id": str(seller["id"]),
    }).json()
    resp = client.get(f"/products/{created['id']}")
    assert resp.status_code == 200
    assert resp.json()["title"] == "Solo"


def test_get_product_not_found(client):
    assert client.get("/products/9999").status_code == 404


def test_get_products_by_seller(client):
    seller = _add_seller(client)
    for i in range(3):
        client.post("/products/add", data={
            "title": f"P{i}", "price": "1", "market_price": "2",
            "seller_id": str(seller["id"]),
        })
    resp = client.get(f"/products/seller/{seller['id']}")
    assert resp.status_code == 200
    assert len(resp.json()) == 3


def test_get_products_by_invalid_seller(client):
    assert client.get("/products/seller/9999").status_code == 404
