"""
routes/admin.py — Admin control layer.

Separate approve / reject / spam endpoints for Swagger clarity.
All actions return AdminActionResponse showing downstream effects.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from config import (
    CAUTION_THRESHOLD,
    VALID_COMPLAINT_REWARD,
    SPAM_COMPLAINT_PENALTY,
    RESOLUTION_PENALTY,
)
from database import get_db
from models import Complaint, Seller, Buyer
from schemas import (
    ComplaintOut,
    AdminComplaintAction,
    AdminActionResponse,
    AdminStatus,
    RecalculateResponse,
)
from fraud_engine import recalculate_trust_score, evaluate_current_risk

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["6. Admin"])

_BUYER_MIN = 20
_BUYER_MAX = 100


def _clamp(score: int) -> int:
    return max(_BUYER_MIN, min(_BUYER_MAX, score))


def _build_action_response(
    complaint: Complaint,
    buyer: Optional[Buyer],
    seller: Optional[Seller],
    action: str,
    credibility_change: int,
) -> AdminActionResponse:
    return AdminActionResponse(
        complaint=complaint,
        buyer_credibility_after=buyer.credibility_score if buyer else 100,
        seller_trust_after=seller.trust_score if seller else 100,
        action_taken=action,
        credibility_change=credibility_change,
    )


# ── List complaints ───────────────────────────────────────────────────────────

@router.get(
    "/complaints",
    response_model=list[ComplaintOut],
    summary="List all complaints (admin view)",
    description="""
Returns complaints with optional filters. Combine filters to triage efficiently.

**Common workflows:**
- Pending review: `admin_status = pending`
- All open with images: `status = open`
- Specific seller complaints: `seller_id = 1`

**admin_status values:** pending → approved | rejected | spam
""",
)
def list_complaints(
    status: Optional[str] = Query(
        default=None,
        description="Filter by complaint status: open | resolved",
    ),
    admin_status: Optional[AdminStatus] = Query(
        default=None,
        description="Filter by admin review status. 'pending' = awaiting your action",
    ),
    seller_id: Optional[int] = Query(
        default=None,
        description="Filter to a specific seller (use their numeric ID)",
    ),
    skip:  int = Query(default=0,   ge=0, description="Records to skip"),
    limit: int = Query(default=100, ge=1, le=500, description="Max records to return"),
    db: Session = Depends(get_db),
):
    q = db.query(Complaint)
    if status in {"open", "resolved"}:
        q = q.filter(Complaint.status == status)
    if admin_status:
        q = q.filter(Complaint.admin_status == admin_status.value)
    if seller_id:
        q = q.filter(Complaint.seller_id == seller_id)
    return q.offset(skip).limit(limit).all()


@router.get(
    "/complaints/{complaint_id}",
    response_model=ComplaintOut,
    summary="Get complaint detail (admin view)",
    description="Full complaint details including mismatch score, severity, and all status fields.",
)
def get_complaint_admin(complaint_id: int, db: Session = Depends(get_db)):
    c = db.query(Complaint).filter(Complaint.id == complaint_id).first()
    if not c:
        raise HTTPException(404, f"Complaint {complaint_id} not found")
    return c


# ── Individual action endpoints (one button per action in Swagger) ─────────

@router.put(
    "/complaints/{complaint_id}/approve",
    response_model=AdminActionResponse,
    summary="✅ Approve a complaint",
    description="""
Mark a complaint as valid and approved.

**Effects:**
- `admin_status` → `approved`
- Buyer credibility: **+5** (rewarded for honest reporting)
- Seller trust score: **recalculated** (complaint now fully counted in feature vector)

**When to approve:** The complaint is genuine — the buyer received a different, fake, or damaged product.

Can only be used when `admin_status = "pending"`. Returns 400 if already actioned.
""",
)
def approve_complaint(complaint_id: int, db: Session = Depends(get_db)):
    complaint = db.query(Complaint).filter(Complaint.id == complaint_id).first()
    if not complaint:
        raise HTTPException(404, f"Complaint {complaint_id} not found")
    if complaint.admin_status != "pending":
        raise HTTPException(400, f"Complaint already actioned: {complaint.admin_status}. Cannot re-action.")

    buyer  = db.query(Buyer).filter(Buyer.id == complaint.buyer_id).first()
    seller = db.query(Seller).filter(Seller.id == complaint.seller_id).first()

    complaint.admin_status = "approved"
    credibility_change = VALID_COMPLAINT_REWARD
    if buyer:
        buyer.credibility_score = _clamp(buyer.credibility_score + VALID_COMPLAINT_REWARD)

    recalculate_trust_score(db, complaint.seller_id)
    db.commit()
    db.refresh(complaint)
    if seller: db.refresh(seller)

    logger.info("Admin APPROVED complaint %d — buyer %d cred +%d", complaint_id, complaint.buyer_id, VALID_COMPLAINT_REWARD)
    return _build_action_response(complaint, buyer, seller, "approve", credibility_change)


@router.put(
    "/complaints/{complaint_id}/reject",
    response_model=AdminActionResponse,
    summary="❌ Reject a complaint",
    description="""
Mark a complaint as invalid and rejected.

**Effects:**
- `admin_status` → `rejected`
- `status` → `resolved` (complaint closed)
- Buyer credibility: **-3** (penalised for filing an invalid complaint)
- Seller trust score: **recalculated** (rejected complaint contributes at 20% decay)

**When to reject:** The complaint is unfounded — the seller delivered what was advertised.

Can only be used when `admin_status = "pending"`.
""",
)
def reject_complaint(complaint_id: int, db: Session = Depends(get_db)):
    complaint = db.query(Complaint).filter(Complaint.id == complaint_id).first()
    if not complaint:
        raise HTTPException(404, f"Complaint {complaint_id} not found")
    if complaint.admin_status != "pending":
        raise HTTPException(400, f"Complaint already actioned: {complaint.admin_status}")

    buyer  = db.query(Buyer).filter(Buyer.id == complaint.buyer_id).first()
    seller = db.query(Seller).filter(Seller.id == complaint.seller_id).first()

    complaint.admin_status = "rejected"
    complaint.status = "resolved"
    credibility_change = -RESOLUTION_PENALTY
    if buyer:
        buyer.credibility_score = _clamp(buyer.credibility_score - RESOLUTION_PENALTY)

    recalculate_trust_score(db, complaint.seller_id)
    db.commit()
    db.refresh(complaint)
    if seller: db.refresh(seller)

    logger.info("Admin REJECTED complaint %d — buyer %d cred -%d", complaint_id, complaint.buyer_id, RESOLUTION_PENALTY)
    return _build_action_response(complaint, buyer, seller, "reject", credibility_change)


@router.put(
    "/complaints/{complaint_id}/spam",
    response_model=AdminActionResponse,
    summary="🚫 Mark complaint as spam",
    description="""
Mark a complaint as fraudulent spam.

**Effects:**
- `admin_status` → `spam`
- `status` → `resolved`
- Buyer credibility: **-8** (heavy penalty — strongest deterrent)
- Buyer `spam_flag_count`: **+1** (tracked separately for monitoring repeat offenders)
- Seller trust score: **recalculated** (spam complaint contributes at 20% decay)

**When to mark spam:** The buyer filed a complaint maliciously to harm the seller,
or submitted duplicate/identical complaints about the same product.

Can only be used when `admin_status = "pending"`.
""",
)
def spam_complaint(complaint_id: int, db: Session = Depends(get_db)):
    complaint = db.query(Complaint).filter(Complaint.id == complaint_id).first()
    if not complaint:
        raise HTTPException(404, f"Complaint {complaint_id} not found")
    if complaint.admin_status != "pending":
        raise HTTPException(400, f"Complaint already actioned: {complaint.admin_status}")

    buyer  = db.query(Buyer).filter(Buyer.id == complaint.buyer_id).first()
    seller = db.query(Seller).filter(Seller.id == complaint.seller_id).first()

    complaint.admin_status = "spam"
    complaint.status = "resolved"
    credibility_change = -SPAM_COMPLAINT_PENALTY
    if buyer:
        buyer.credibility_score = _clamp(buyer.credibility_score - SPAM_COMPLAINT_PENALTY)
        buyer.spam_flag_count += 1

    recalculate_trust_score(db, complaint.seller_id)
    db.commit()
    db.refresh(complaint)
    if seller: db.refresh(seller)

    logger.info("Admin SPAM complaint %d — buyer %d cred -%d spam_count+1", complaint_id, complaint.buyer_id, SPAM_COMPLAINT_PENALTY)
    return _build_action_response(complaint, buyer, seller, "spam", credibility_change)


# ── Combined action endpoint (kept for API backward compatibility) ─────────

@router.put(
    "/complaints/{complaint_id}/action",
    response_model=AdminActionResponse,
    summary="Admin action (approve / reject / spam) — combined endpoint",
    description="""
Combined admin action endpoint. For clearer Swagger UX, prefer the dedicated endpoints:
- `PUT /admin/complaints/{id}/approve`
- `PUT /admin/complaints/{id}/reject`
- `PUT /admin/complaints/{id}/spam`

**Body:** `{"action": "approve"}` or `{"action": "reject"}` or `{"action": "spam"}`
""",
)
def complaint_action(
    complaint_id: int,
    payload: AdminComplaintAction,
    db: Session = Depends(get_db),
):
    handlers = {
        "approve": approve_complaint,
        "reject":  reject_complaint,
        "spam":    spam_complaint,
    }
    handler = handlers.get(payload.action.value if hasattr(payload.action, "value") else payload.action)
    if not handler:
        raise HTTPException(400, "action must be 'approve', 'reject', or 'spam'")
    return handler(complaint_id, db)


# ── Trust recalculation ───────────────────────────────────────────────────────

@router.post(
    "/sellers/{seller_id}/recalculate",
    response_model=RecalculateResponse,
    summary="Force seller trust score recalculation",
    description="""
Manually trigger a complete trust score recalculation for a seller.

**When to use:**
- After bulk complaint resolution
- After correcting data errors
- To verify trust score reflects current state

The recalculation uses all complaints (open + resolved with 20% decay) and the
7-feature weighted scoring system. The new score is persisted immediately.
""",
)
def trigger_recalculate(seller_id: int, db: Session = Depends(get_db)):
    seller = db.query(Seller).filter(Seller.id == seller_id).first()
    if not seller:
        raise HTTPException(404, f"Seller {seller_id} not found")

    new_score = recalculate_trust_score(db, seller_id)
    db.commit()
    logger.info("Admin recalculated seller %d → score=%d", seller_id, new_score)

    return RecalculateResponse(
        seller_id=seller_id,
        trust_score=new_score,
        message=f"Seller {seller_id} trust score recalculated to {new_score}/100",
    )


# ── Suspicious sellers ────────────────────────────────────────────────────────

@router.get(
    "/sellers/suspicious",
    summary="List sellers at or below trust threshold",
    description="""
Returns sellers whose trust score is at or below the threshold, ordered by score ascending (worst first).

**Default threshold:** 40 (Caution boundary — sellers in Caution or High Risk range)

Each result includes `open_complaint_count` for quick triage priority.

**Risk levels:**
- trust_score < 40 → High Risk
- trust_score 40–69 → Caution
- trust_score ≥ 70 → Safe
""",
)
def get_suspicious_sellers(
    threshold: int = Query(
        default=CAUTION_THRESHOLD,
        ge=0,
        le=100,
        description="Show sellers at or below this trust score (0–100). Default: 40 (Caution boundary)",
    ),
    db: Session = Depends(get_db),
):
    sellers = (
        db.query(Seller)
        .filter(Seller.trust_score <= threshold)
        .order_by(Seller.trust_score.asc())
        .all()
    )
    result = []
    for s in sellers:
        open_count = (
            db.query(Complaint)
            .filter(Complaint.seller_id == s.id, Complaint.status == "open")
            .count()
        )
        result.append({
            "id":                   s.id,
            "name":                 s.name,
            "trust_score":          s.trust_score,
            "risk_level":           "High Risk" if s.trust_score < 40 else "Caution",
            "account_age_days":     s.account_age_days,
            "open_complaint_count": open_count,
        })
    return result


# ── Seller signals / feature vector debug ────────────────────────────────────

@router.get(
    "/sellers/{seller_id}/signals",
    summary="View full feature vector for a seller",
    description="""
Returns the complete feature-vector breakdown that drove the seller's trust score.

**Response includes:**
- `signals`: All 7 normalised feature values used in the scoring formula
- `feature_weights`: The weight multiplied against each feature
- `trust_score`: Current computed score

**Formula:** `trust_score = (1 - weighted_risk) × 100`
where `weighted_risk = Σ(feature_value × feature_weight)`

Use this to understand exactly why a seller has a particular score.
For example, if `mean_visual_mismatch = 0.85` with weight 0.20,
it contributes 0.17 to the weighted_risk (17 risk points).
""",
)
def get_seller_signals(seller_id: int, db: Session = Depends(get_db)):
    result = evaluate_current_risk(db, seller_id)
    if result is None:
        raise HTTPException(404, f"Seller {seller_id} not found")

    signals = result["signals"]
    import config as cfg
    feature_weights = dict(cfg.FEATURE_WEIGHTS)

    contributions = {
        k: round(signals.features.get(k, 0.0) * w, 4)
        for k, w in feature_weights.items()
    }

    return {
        "seller_id":        seller_id,
        "trust_score":      result["fresh_trust_score"],
        "weighted_risk":    round(signals.weighted_risk, 4),
        "signals":          signals.to_dict(),
        "feature_weights":  feature_weights,
        "contributions":    contributions,
        "formula":          "trust_score = round((1 - weighted_risk) × 100)",
    }
