"""routes/buyers.py — Buyer CRUD with full create/read/update/delete."""

import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from models import Buyer, Complaint
from schemas import BuyerCreate, BuyerOut

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/buyers", tags=["2. Buyers"])


@router.post("/add", response_model=BuyerOut, status_code=201, summary="Create a new buyer")
def add_buyer(payload: BuyerCreate, db: Session = Depends(get_db)):
    buyer = Buyer(name=payload.name)
    db.add(buyer); db.commit(); db.refresh(buyer)
    return buyer


@router.get("/all", response_model=list[BuyerOut], summary="List all buyers")
def get_all_buyers(
    skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    return db.query(Buyer).offset(skip).limit(limit).all()


@router.get("/{buyer_id}", response_model=BuyerOut, summary="Get buyer by ID")
def get_buyer(buyer_id: int, db: Session = Depends(get_db)):
    b = db.query(Buyer).filter(Buyer.id == buyer_id).first()
    if not b:
        raise HTTPException(404, f"Buyer {buyer_id} not found")
    return b


@router.put("/{buyer_id}", response_model=BuyerOut, summary="Update buyer name")
def update_buyer(buyer_id: int, payload: BuyerCreate, db: Session = Depends(get_db)):
    b = db.query(Buyer).filter(Buyer.id == buyer_id).first()
    if not b:
        raise HTTPException(404, f"Buyer {buyer_id} not found")
    b.name = payload.name
    db.commit(); db.refresh(b)
    return b


@router.delete("/{buyer_id}", summary="Delete a buyer and their complaints")
def delete_buyer(buyer_id: int, db: Session = Depends(get_db)):
    b = db.query(Buyer).filter(Buyer.id == buyer_id).first()
    if not b:
        raise HTTPException(404, f"Buyer {buyer_id} not found")
    count = db.query(Complaint).filter(Complaint.buyer_id == buyer_id).count()
    db.query(Complaint).filter(Complaint.buyer_id == buyer_id).delete()
    db.delete(b); db.commit()
    return {"message": f"Buyer {buyer_id} deleted", "deleted_complaints": count}
