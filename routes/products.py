"""routes/products.py — Product CRUD with full create/read/update/delete."""

import logging
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from sqlalchemy.orm import Session

from utils.file_handler import validate_extension, read_file_safe, generate_filename, save_file
from config import UPLOAD_DIR_PRODUCTS
from database import get_db
from models import Product, Seller, Complaint
from schemas import ProductOut

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/products", tags=["3. Products"])


@router.post("/add", response_model=ProductOut, status_code=201, summary="Add a product listing")
async def add_product(
    title: str        = Form(..., description="Product title"),
    price: float      = Form(..., gt=0, description="Selling price in USD"),
    market_price: float = Form(..., gt=0, description="Market / retail price in USD"),
    seller_id: int    = Form(..., gt=0, description="Seller ID"),
    image: UploadFile | None = File(default=None, description="Product image (jpg/png/webp, max 5MB)"),
    db: Session = Depends(get_db),
):
    seller = db.query(Seller).filter(Seller.id == seller_id).first()
    if not seller:
        raise HTTPException(404, "Seller not found")
    image_path = ""
    if image and image.filename:
        ext = validate_extension(image.filename)
        content = await read_file_safe(image)
        filename = generate_filename(ext)
        save_file(content, UPLOAD_DIR_PRODUCTS, filename)
        image_path = f"uploads/products/{filename}"
    product = Product(title=title, price=price, market_price=market_price,
                      seller_id=seller_id, image_path=image_path)
    db.add(product); db.commit(); db.refresh(product)
    logger.info("Product created id=%d", product.id)
    return product


@router.get("/all", response_model=list[ProductOut], summary="List all products")
def get_all_products(
    skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    return db.query(Product).offset(skip).limit(limit).all()


@router.get("/seller/{seller_id}", response_model=list[ProductOut], summary="Products by seller")
def get_products_by_seller(seller_id: int, db: Session = Depends(get_db)):
    if not db.query(Seller).filter(Seller.id == seller_id).first():
        raise HTTPException(404, "Seller not found")
    return db.query(Product).filter(Product.seller_id == seller_id).all()


@router.get("/{product_id}", response_model=ProductOut, summary="Get product by ID")
def get_product(product_id: int, db: Session = Depends(get_db)):
    p = db.query(Product).filter(Product.id == product_id).first()
    if not p:
        raise HTTPException(404, f"Product {product_id} not found")
    return p


@router.put("/{product_id}", response_model=ProductOut, summary="Update product title or pricing")
async def update_product(
    product_id: int,
    title: str          = Form(..., description="Updated title"),
    price: float        = Form(..., gt=0, description="Updated selling price"),
    market_price: float = Form(..., gt=0, description="Updated market price"),
    image: UploadFile | None = File(default=None, description="Replace product image (optional)"),
    db: Session = Depends(get_db),
):
    p = db.query(Product).filter(Product.id == product_id).first()
    if not p:
        raise HTTPException(404, f"Product {product_id} not found")
    p.title = title
    p.price = price
    p.market_price = market_price
    if image and image.filename:
        ext = validate_extension(image.filename)
        content = await read_file_safe(image)
        filename = generate_filename(ext)
        save_file(content, UPLOAD_DIR_PRODUCTS, filename)
        p.image_path = f"uploads/products/{filename}"
    db.commit(); db.refresh(p)
    logger.info("Product %d updated", product_id)
    return p


@router.delete("/{product_id}", summary="Delete a product")
def delete_product(product_id: int, db: Session = Depends(get_db)):
    p = db.query(Product).filter(Product.id == product_id).first()
    if not p:
        raise HTTPException(404, f"Product {product_id} not found")
    count = db.query(Complaint).filter(Complaint.product_id == product_id).count()
    db.query(Complaint).filter(Complaint.product_id == product_id).delete()
    db.delete(p); db.commit()
    return {"message": f"Product {product_id} deleted", "deleted_complaints": count}
