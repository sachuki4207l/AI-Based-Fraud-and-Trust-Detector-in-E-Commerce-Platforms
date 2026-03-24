"""
routes/complaints.py — Complaint lifecycle endpoints.

Non-blocking: complaint saved immediately, AI runs in background.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, UploadFile, File, Form
from sqlalchemy.orm import Session

from config import (
    UPLOAD_DIR_COMPLAINTS,
    ALLOWED_IMAGE_EXTENSIONS,
    MAX_IMAGE_SIZE_BYTES,
    BUYER_CREDIBILITY_MIN,
    BUYER_CREDIBILITY_MAX,
    COMPLAINT_SUBMISSION_PENALTY,
    RESOLUTION_PENALTY,
    RESOLUTION_REWARD_LOW_SEV,
)
from database import get_db
from models import Buyer, Seller, Complaint, Product
from schemas import ComplaintOut, ComplaintCreateResponse, ComplaintUpdate, ComplaintStatus
from worker import process_complaint_task
from utils.file_handler import validate_extension, generate_filename, save_file

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/complaints", tags=["4. Complaints"])

BASE_DIR = Path(__file__).resolve().parent.parent


def _clamp_credibility(score: int) -> int:
    return max(BUYER_CREDIBILITY_MIN, min(BUYER_CREDIBILITY_MAX, score))


def _save_complaint_image(upload: UploadFile) -> tuple[str, Path]:
    ext = validate_extension(upload.filename or "")
    content = upload.file.read()
    if len(content) > MAX_IMAGE_SIZE_BYTES:
        raise HTTPException(413, f"Image too large. Max {MAX_IMAGE_SIZE_BYTES//(1024*1024)} MB.")
    filename = generate_filename(ext)
    abs_path = save_file(content, UPLOAD_DIR_COMPLAINTS, filename)
    return f"uploads/complaints/{filename}", abs_path


# ── Submit complaint (non-blocking) ──────────────────────────────────────────

@router.post(
    "/add",
    response_model=ComplaintCreateResponse,
    status_code=201,
    summary="Submit a complaint with optional image evidence",
    description="""
File a complaint against a seller for a specific product.

**Non-blocking:** The API responds immediately with `processing_status = "queued"`.
The AI processing pipeline then runs in the background:
1. AI image comparison (CLIP/ResNet) — compares evidence photo to product listing
2. Auto-severity computation (AI mismatch + keyword analysis + price anomaly)
3. Seller trust score recalculation (feature-vector scoring)

**Poll for results:** Use `GET /complaints/{complaint_id}` and check `processing_status`.
When it shows `"done"`, the `severity_level` and `visual_mismatch_score` are final.

**Auto-severity system:** You do NOT set severity — the system computes it from:
- Visual mismatch score × 3 (0–3 pts)
- Keyword analysis of complaint_text (0–2 pts: "fake"/"scam"/"counterfeit" = +3, "damaged"/"wrong" = +2)
- Price anomaly flag (+1 pt if seller has suspicious pricing)

**Buyer credibility:** Filing a complaint applies a provisional -2 credibility deduction.
Admin approval returns +5. Admin rejection returns -3.

**To test in Swagger:**
1. Use `GET /sellers/all` to get a seller_id
2. Use `GET /products/seller/{id}` to get a product_id for that seller
3. Use `GET /buyers/all` to get a buyer_id
4. Fill in the form fields and optionally upload an evidence photo
5. Copy the returned complaint_id and poll `GET /complaints/{id}`
""",
)
async def add_complaint(
    background_tasks: BackgroundTasks,
    buyer_id: int = Form(
        ...,
        gt=0,
        description="ID of the buyer filing this complaint. Use GET /buyers/all to find valid IDs",
        examples=[1],
    ),
    seller_id: int = Form(
        ...,
        gt=0,
        description="ID of the seller being complained about. Must be the seller who listed the product",
        examples=[1],
    ),
    product_id: int = Form(
        ...,
        gt=0,
        description="ID of the specific product involved. Use GET /products/seller/{seller_id} to find valid product IDs",
        examples=[1],
    ),
    complaint_text: str = Form(
        default="The product I received looks completely different from what was listed. It appears to be a counterfeit item.",
        min_length=5,
        description="Detailed description of the issue. Use specific keywords (fake, scam, damaged, wrong) to influence auto-severity calculation",
    ),
    received_image: UploadFile | None = File(
        default=None,
        description="Photo of the item you actually received (jpg/jpeg/png/webp, max 5 MB). The AI will compare this to the seller's listing image to detect visual mismatch",
    ),
    db: Session = Depends(get_db),
):
    buyer = db.query(Buyer).filter(Buyer.id == buyer_id).first()
    if not buyer:
        raise HTTPException(404, f"Buyer {buyer_id} not found. Create one at POST /buyers/add")

    seller = db.query(Seller).filter(Seller.id == seller_id).first()
    if not seller:
        raise HTTPException(404, f"Seller {seller_id} not found")

    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(404, f"Product {product_id} not found. Use GET /products/seller/{seller_id} to list products")

    if product.seller_id != seller_id:
        raise HTTPException(
            400,
            f"Product {product_id} belongs to seller {product.seller_id}, not seller {seller_id}. "
            "Use GET /products/seller/{seller_id} to find products for this seller."
        )

    image_rel_path: Optional[str] = None
    if received_image and received_image.filename:
        image_rel_path, _ = _save_complaint_image(received_image)

    complaint = Complaint(
        buyer_id=buyer_id,
        seller_id=seller_id,
        product_id=product_id,
        complaint_text=complaint_text,
        severity_level=0,
        received_image_path=image_rel_path,
        visual_mismatch_score=0.0,
        processing_status="queued",
        admin_status="pending",
    )
    db.add(complaint)
    buyer.credibility_score = _clamp_credibility(
        buyer.credibility_score - COMPLAINT_SUBMISSION_PENALTY
    )
    db.commit()
    db.refresh(complaint)

    background_tasks.add_task(process_complaint_task, complaint.id)
    logger.info("Complaint %d queued (seller=%d buyer=%d)", complaint.id, seller_id, buyer_id)

    return ComplaintCreateResponse(
        complaint_id=complaint.id,
        processing_status=complaint.processing_status,  # type: ignore[arg-type]
        message=f"Complaint #{complaint.id} received and queued for AI processing. "
                f"Poll GET /complaints/{complaint.id} until processing_status = 'done' for final severity and mismatch score.",
        complaint=complaint,
    )


# ── Update complaint ──────────────────────────────────────────────────────────

@router.put(
    "/update",
    response_model=ComplaintOut,
    summary="Update or resolve a complaint",
    description="""
Update a complaint's text or change its status to resolved.

**Resolving a complaint** (`status = "resolved"`):
- Triggers seller trust score recalculation
- Applies buyer credibility adjustment: -3 penalty (partial refund of +1 if severity ≤ 2)
- The complaint still contributes to the seller's historical trust score at 20% decay weight

**Note:** Severity is managed by the system and cannot be changed here.
Admin actions (approve/reject/spam) are handled by the `/admin/` endpoints.
""",
)
def update_complaint(payload: ComplaintUpdate, db: Session = Depends(get_db)):
    complaint = db.query(Complaint).filter(Complaint.id == payload.complaint_id).first()
    if not complaint:
        raise HTTPException(404, f"Complaint {payload.complaint_id} not found")

    buyer     = db.query(Buyer).filter(Buyer.id == complaint.buyer_id).first()
    old_status = complaint.status

    if payload.complaint_text is not None:
        complaint.complaint_text = payload.complaint_text

    if payload.status is not None:
        complaint.status = payload.status.value if hasattr(payload.status, "value") else payload.status

    complaint.updated_at = datetime.now(timezone.utc)

    from fraud_engine import recalculate_trust_score
    recalculate_trust_score(db, complaint.seller_id)

    if old_status == "open" and complaint.status == "resolved" and buyer:
        buyer.credibility_score = _clamp_credibility(
            buyer.credibility_score - RESOLUTION_PENALTY
        )
        if complaint.severity_level <= 2:
            buyer.credibility_score = _clamp_credibility(
                buyer.credibility_score + RESOLUTION_REWARD_LOW_SEV
            )
        logger.info("Complaint %d resolved. Buyer %d credibility → %d",
                    complaint.id, buyer.id, buyer.credibility_score)

    db.commit()
    db.refresh(complaint)
    return complaint


# ── Read endpoints ────────────────────────────────────────────────────────────

@router.get(
    "/all",
    response_model=list[ComplaintOut],
    summary="List all complaints",
    description="Returns all complaints across all sellers. Use skip/limit for pagination.",
)
def get_all_complaints(
    skip:  int = Query(default=0,   ge=0,  description="Records to skip"),
    limit: int = Query(default=100, ge=1, le=500, description="Max records to return"),
    db: Session = Depends(get_db),
):
    return db.query(Complaint).offset(skip).limit(limit).all()


@router.get(
    "/seller/{seller_id}",
    response_model=list[ComplaintOut],
    summary="Get complaints for a specific seller",
    description="Returns all complaints against a seller. Filter by status to see only open or resolved complaints.",
)
def get_complaints_by_seller(
    seller_id: int,
    status: Optional[ComplaintStatus] = Query(
        default=None,
        description="Filter by complaint status: 'open' or 'resolved'. Leave blank for all.",
    ),
    db: Session = Depends(get_db),
):
    seller = db.query(Seller).filter(Seller.id == seller_id).first()
    if not seller:
        raise HTTPException(404, f"Seller {seller_id} not found")
    query = db.query(Complaint).filter(Complaint.seller_id == seller_id)
    if status:
        query = query.filter(Complaint.status == status.value)
    return query.all()


@router.get(
    "/{complaint_id}",
    response_model=ComplaintOut,
    summary="Track a complaint by ID",
    description="""
Fetch current state of a complaint. Use this to poll for AI processing completion.

**Processing lifecycle:**
- `processing_status = "queued"` → AI not yet started
- `processing_status = "done"` → `severity_level` and `visual_mismatch_score` are final

**Visual mismatch score interpretation:**
- 0.0–0.3 → Images look similar (likely same product)
- 0.3–0.6 → Some difference detected
- 0.6–1.0 → Significant mismatch (likely different product sent)
""",
)
def get_complaint(complaint_id: int, db: Session = Depends(get_db)):
    complaint = db.query(Complaint).filter(Complaint.id == complaint_id).first()
    if not complaint:
        raise HTTPException(404, f"Complaint {complaint_id} not found")
    return complaint
