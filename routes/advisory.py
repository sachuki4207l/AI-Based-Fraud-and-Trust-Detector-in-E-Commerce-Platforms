"""
routes/advisory.py — Real-time seller trust advisory with full explainability.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from config import SAFE_THRESHOLD, CAUTION_THRESHOLD, VISUAL_MISMATCH_THRESHOLD
from database import get_db
from models import Seller, Complaint
from schemas import AdvisoryOut, SignalsOut
from fraud_engine import evaluate_current_risk
from ai_vision import get_model_name

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/advisory", tags=["5. Advisory"])


def _risk_level(score: int) -> str:
    if score >= SAFE_THRESHOLD:    return "Safe"
    if score >= CAUTION_THRESHOLD: return "Caution"
    return "High Risk"


_RECOMMENDATIONS = {
    "Safe":      "Safe to purchase from this seller",
    "Caution":   "Proceed with caution when purchasing",
    "High Risk": "Avoid purchase from this seller",
}
_ANOMALY_SAFE_RECOMMENDATION = "Safe to purchase, but review pricing carefully before buying"

_RANK_HIGH_SEVERITY    = 0
_RANK_VISUAL_MISMATCH  = 1
_RANK_SUSPICIOUS_PRICE = 2
_RANK_NEW_ACCOUNT      = 3
_RANK_HAS_COMPLAINTS   = 4


def _build_reasons(seller, open_complaints, signals, is_anomaly_safe):
    ranked = []
    if any(c.severity_level >= 4 for c in open_complaints):
        ranked.append((_RANK_HIGH_SEVERITY, "High severity unresolved complaints detected"))
    if signals.mean_visual_mismatch >= VISUAL_MISMATCH_THRESHOLD:
        ranked.append((_RANK_VISUAL_MISMATCH,
            f"AI visual mismatch detected (score: {signals.mean_visual_mismatch:.2f})"))
    if signals.has_price_anomaly:
        msg = ("Seller exhibits unusual pricing patterns"
               if is_anomaly_safe else
               "Seller exhibits suspicious pricing behaviour")
        ranked.append((_RANK_SUSPICIOUS_PRICE, msg))
    if seller.account_age_days < 30:
        ranked.append((_RANK_NEW_ACCOUNT, "Seller account is relatively new"))
    if signals.open_complaints > 0:
        label = "complaint" if signals.open_complaints == 1 else "complaints"
        ranked.append((_RANK_HAS_COMPLAINTS,
            f"Seller has {signals.open_complaints} active {label}"))
    if signals.complaint_frequency > 1.0:
        ranked.append((_RANK_HAS_COMPLAINTS,
            f"High complaint frequency ({signals.complaint_frequency:.1f} per 30 days)"))
    ranked.sort(key=lambda r: r[0])
    return [text for _, text in ranked]


@router.get(
    "/seller/{seller_id}",
    response_model=AdvisoryOut,
    summary="Get real-time trust advisory for a seller",
    description="""
Returns a complete trust assessment for a seller powered by the real-time feature-vector engine.

**Trust score layers:**
- This endpoint uses **Layer 2 (real-time)** — open complaints only. Resolving a complaint improves the score immediately.
- `GET /sellers/{id}` returns the **Layer 1 (historical)** stored score which decays resolved complaints at 20%.

**Response fields:**
- `trust_score`: 0–100. ≥70 = Safe, 40–69 = Caution, <40 = High Risk
- `risk_level`: Human-readable risk category
- `recommendation`: Purchase recommendation text
- `reasons`: Ordered list of risk factors (most important first)
- `signals`: Full feature vector showing exactly which metrics drove the score
- `ai_model_used`: Which AI model computed visual mismatch scores (clip/resnet/none)

**Signals → trust score formula:**
`weighted_risk = Σ(normalised_feature × weight)`
`trust_score = round((1 - weighted_risk) × 100)`

**Feature weights (from config.py):**
- open_complaint_ratio: 25%
- avg_severity: 20%
- mean_visual_mismatch: 20%
- buyer_credibility_weighted_sev: 15%
- price_anomaly_ratio: 10%
- complaint_frequency: 5%
- account_age_penalty: 5%
""",
)
def get_seller_advisory(seller_id: int, db: Session = Depends(get_db)):
    result = evaluate_current_risk(db, seller_id)
    if result is None:
        raise HTTPException(404, f"Seller {seller_id} not found")

    seller        = result["seller"]
    fresh_score   = result["fresh_trust_score"]
    open_cmpls    = db.query(Complaint).filter(
        Complaint.seller_id == seller_id, Complaint.status == "open"
    ).all()
    price_anomaly = result["price_anomaly"]
    signals_obj   = result["signals"]

    risk = _risk_level(fresh_score)
    is_anomaly_safe = (risk == "Safe" and not open_cmpls and price_anomaly)
    recommendation  = _ANOMALY_SAFE_RECOMMENDATION if is_anomaly_safe else _RECOMMENDATIONS[risk]
    reasons = _build_reasons(seller, open_cmpls, signals_obj, is_anomaly_safe)

    signals_out = SignalsOut(
        open_complaints=signals_obj.open_complaints,
        total_complaints=signals_obj.total_complaints,
        avg_severity=signals_obj.avg_severity,
        mean_visual_mismatch=signals_obj.mean_visual_mismatch,
        buyer_credibility_weighted_sev=signals_obj.buyer_credibility_weighted_sev,
        price_anomaly_ratio=signals_obj.price_anomaly_ratio,
        complaint_frequency=signals_obj.complaint_frequency,
        account_age_days=signals_obj.account_age_days,
        has_price_anomaly=signals_obj.has_price_anomaly,
        weighted_risk=signals_obj.weighted_risk,
    )

    logger.info("Advisory: seller=%d score=%d risk=%r", seller_id, fresh_score, risk)

    return AdvisoryOut(
        seller_id=seller.id,
        seller_name=seller.name,
        trust_score=fresh_score,
        risk_level=risk,
        recommendation=recommendation,
        reasons=reasons,
        signals=signals_out,
        open_complaint_count=len(open_cmpls),
        has_price_anomaly=price_anomaly,
        account_age_days=seller.account_age_days,
        ai_model_used=get_model_name(),
    )
