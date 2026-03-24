"""
worker.py — Background task processing for the complaint pipeline.

Architecture:
  POST /complaints/add
    → complaint saved immediately with processing_status="queued"
    → HTTP 201 returned to client immediately (non-blocking)
    → FastAPI BackgroundTasks schedules process_complaint_task()
    → Worker runs: AI comparison → auto-severity → trust recalc → DB update

This decouples heavy AI inference from the request cycle.
For production scale, swap FastAPI BackgroundTasks for Celery + Redis:
  @celery_app.task
  def process_complaint_task(complaint_id: int): ...
"""

import logging
from pathlib import Path

from sqlalchemy.orm import Session

from config import BASE_DIR
from database import SessionLocal
from ai_vision import compare_images
from text_analyzer import compute_auto_severity
from fraud_engine import recalculate_trust_score, has_price_anomaly

logger = logging.getLogger(__name__)


def process_complaint_task(complaint_id: int) -> None:
    """
    Background worker entry point.

    Steps:
      1. Load complaint from DB.
      2. Run AI image comparison (if evidence image present).
      3. Compute auto-severity from mismatch score + complaint text + price anomaly.
      4. Persist mismatch score and severity back to complaint.
      5. Recalculate seller trust score (Layer 1).
      6. Mark complaint processing_status = "done".
      7. Commit everything in one transaction.

    Uses its own DB session so it can run safely in a background thread.
    """
    db: Session = SessionLocal()
    try:
        from models import Complaint, Product, Seller

        complaint = db.query(Complaint).filter(Complaint.id == complaint_id).first()
        if complaint is None:
            logger.error("worker: complaint %d not found", complaint_id)
            return

        logger.info("worker: processing complaint %d", complaint_id)

        # ── AI image comparison ────────────────────────────────────────────────
        mismatch_score = 0.0
        product = db.query(Product).filter(Product.id == complaint.product_id).first()

        if complaint.received_image_path and product and product.image_path:
            product_abs = BASE_DIR / product.image_path
            complaint_abs = BASE_DIR / complaint.received_image_path

            if product_abs.exists() and complaint_abs.exists():
                try:
                    mismatch_score = compare_images(
                        str(product_abs),
                        str(complaint_abs),
                        db=db,
                    )
                    logger.info(
                        "worker: complaint %d AI mismatch=%.4f",
                        complaint_id, mismatch_score,
                    )
                except Exception as exc:
                    logger.error("worker: AI comparison failed for complaint %d: %s", complaint_id, exc)

        complaint.visual_mismatch_score = mismatch_score

        # ── Auto-severity ──────────────────────────────────────────────────────
        seller = db.query(Seller).filter(Seller.id == complaint.seller_id).first()
        products = db.query(Product).filter(Product.seller_id == complaint.seller_id).all()
        price_anom = has_price_anomaly(products)

        severity = compute_auto_severity(
            mismatch_score=mismatch_score,
            complaint_text=complaint.complaint_text,
            has_price_anomaly=price_anom,
        )
        complaint.severity_level = severity
        logger.info("worker: complaint %d auto_severity=%d", complaint_id, severity)

        # ── Seller trust recalculation ─────────────────────────────────────────
        recalculate_trust_score(db, complaint.seller_id)

        # ── Mark as done ───────────────────────────────────────────────────────
        complaint.processing_status = "done"

        db.commit()
        logger.info("worker: complaint %d processing complete", complaint_id)

    except Exception as exc:
        db.rollback()
        logger.error("worker: unhandled error for complaint %d: %s", complaint_id, exc, exc_info=True)
    finally:
        db.close()
