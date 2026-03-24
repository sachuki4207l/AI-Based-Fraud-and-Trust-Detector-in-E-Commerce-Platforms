"""routes/sellers.py — Seller CRUD with full create/read/update/delete."""

import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from models import Seller, Complaint, Product
from schemas import SellerCreate, SellerOut

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sellers", tags=["1. Sellers"])


@router.post("/add", response_model=SellerOut, status_code=201,
    summary="Create a new seller")
def add_seller(payload: SellerCreate, db: Session = Depends(get_db)):
    seller = Seller(name=payload.name, account_age_days=payload.account_age_days)
    db.add(seller); db.commit(); db.refresh(seller)
    logger.info("Seller created id=%d", seller.id)
    return seller


@router.get("/all", response_model=list[SellerOut], summary="List all sellers")
def get_all_sellers(
    skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    return db.query(Seller).offset(skip).limit(limit).all()


@router.get("/{seller_id}", response_model=SellerOut, summary="Get seller by ID")
def get_seller(seller_id: int, db: Session = Depends(get_db)):
    s = db.query(Seller).filter(Seller.id == seller_id).first()
    if not s:
        raise HTTPException(404, f"Seller {seller_id} not found")
    return s


@router.put("/{seller_id}", response_model=SellerOut, summary="Update seller name or account age")
def update_seller(seller_id: int, payload: SellerCreate, db: Session = Depends(get_db)):
    s = db.query(Seller).filter(Seller.id == seller_id).first()
    if not s:
        raise HTTPException(404, f"Seller {seller_id} not found")
    s.name = payload.name
    s.account_age_days = payload.account_age_days
    db.commit(); db.refresh(s)
    logger.info("Seller %d updated", seller_id)
    return s


@router.delete("/{seller_id}", summary="Delete a seller and all their data")
def delete_seller(seller_id: int, db: Session = Depends(get_db)):
    s = db.query(Seller).filter(Seller.id == seller_id).first()
    if not s:
        raise HTTPException(404, f"Seller {seller_id} not found")
    complaint_count = db.query(Complaint).filter(Complaint.seller_id == seller_id).count()
    product_count   = db.query(Product).filter(Product.seller_id == seller_id).count()
    # Delete cascades: complaints, products
    db.query(Complaint).filter(Complaint.seller_id == seller_id).delete()
    db.query(Product).filter(Product.seller_id == seller_id).delete()
    db.delete(s); db.commit()
    logger.info("Seller %d deleted (cascade: %d products, %d complaints)", seller_id, product_count, complaint_count)
    return {
        "message": f"Seller {seller_id} deleted",
        "deleted_products": product_count,
        "deleted_complaints": complaint_count,
    }
