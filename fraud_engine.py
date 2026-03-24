"""
fraud_engine.py — Feature-driven trust scoring engine.

Upgraded from prototype rule-based approach to a structured feature-vector
scoring system with full explainability signals.

Architecture
------------
Layer 1 (historical) — recalculate_trust_score()
    Builds a feature vector from ALL complaints (open + resolved with decay),
    normalises each feature to [0,1], applies configured weights, and persists
    the resulting trust_score to the database.

Layer 2 (real-time)  — evaluate_current_risk()
    Read-only. Same feature pipeline but restricted to OPEN complaints only.
    Also returns the full SellerSignals dict for the explainability layer.

Feature vector (7 dimensions)
------------------------------
open_complaint_ratio           open / max(total, 1), capped at 1.0
avg_severity                   mean severity of open complaints / 5
mean_visual_mismatch           mean AI mismatch score of open complaints
buyer_credibility_weighted_sev credibility-adjusted severity mean
price_anomaly_ratio            fraction of products priced anomalously
complaint_frequency            complaints per 30-day window of account life
account_age_penalty            1.0 for brand-new sellers, 0.0 for established
"""

import logging
from dataclasses import dataclass, field, asdict
from typing import Optional

from sqlalchemy.orm import Session

from config import (
    FEATURE_WEIGHTS,
    PRICE_ANOMALY_RATIO,
    NEW_ACCOUNT_DAYS,
    SAFE_THRESHOLD,
    CAUTION_THRESHOLD,
    RESOLVED_DECAY_FACTOR,
)
from models import Seller, Product, Complaint

logger = logging.getLogger(__name__)


# ── Explainability signals dataclass ─────────────────────────────────────────

@dataclass
class SellerSignals:
    """
    Structured snapshot of all signals used to compute a seller's trust score.
    Returned alongside the trust score so advisory and admin endpoints can
    surface transparent, debuggable explanations.
    """
    open_complaints:               int   = 0
    total_complaints:              int   = 0
    avg_severity:                  float = 0.0
    mean_visual_mismatch:          float = 0.0
    buyer_credibility_weighted_sev:float = 0.0
    price_anomaly_ratio:           float = 0.0
    complaint_frequency:           float = 0.0   # complaints per 30 days
    account_age_days:              int   = 0
    account_age_penalty:           float = 0.0   # 1.0 = new, 0.0 = established
    has_price_anomaly:             bool  = False
    # Normalised feature values [0, 1]
    features: dict = field(default_factory=dict)
    # Final weighted risk before conversion to trust score
    weighted_risk: float = 0.0

    def to_dict(self) -> dict:
        d = asdict(self)
        # Round floats for clean JSON output
        for k, v in d.items():
            if isinstance(v, float):
                d[k] = round(v, 4)
        if isinstance(d.get("features"), dict):
            d["features"] = {k: round(v, 4) for k, v in d["features"].items()}
        return d


# ── Feature computation ───────────────────────────────────────────────────────

def _credibility_multiplier(credibility_score: int) -> float:
    """credibility 20→0.60, 100→1.00"""
    return 0.5 + (max(20, min(100, credibility_score)) / 200.0)


def _compute_features(
    seller: Seller,
    complaints: list[Complaint],
    products: list[Product],
    open_only: bool,
) -> tuple[dict[str, float], SellerSignals]:
    """
    Build the normalised feature vector for a seller.

    Parameters
    ----------
    open_only : if True, only open complaints are used (Layer 2 / advisory).
                if False, resolved complaints contribute with decay (Layer 1).

    Returns (feature_dict, SellerSignals)
    """
    working = [c for c in complaints if not open_only or c.status == "open"]
    open_complaints = [c for c in complaints if c.status == "open"]
    total = len(complaints)
    n = len(working)

    # ── avg_severity ──────────────────────────────────────────────────────────
    if n > 0:
        severities = []
        for c in working:
            w = c.severity_level
            if not open_only and c.status == "resolved":
                w = w * RESOLVED_DECAY_FACTOR
            severities.append(w)
        avg_sev = sum(severities) / n
    else:
        avg_sev = 0.0

    # ── mean_visual_mismatch ──────────────────────────────────────────────────
    mismatch_scores = [c.visual_mismatch_score or 0.0 for c in working]
    mean_mismatch = sum(mismatch_scores) / n if n > 0 else 0.0

    # ── buyer_credibility_weighted_sev ────────────────────────────────────────
    if n > 0:
        weighted_total = 0.0
        for c in working:
            cred = c.buyer.credibility_score if c.buyer else 100
            mult = _credibility_multiplier(cred)
            w = c.severity_level
            if not open_only and c.status == "resolved":
                w *= RESOLVED_DECAY_FACTOR
            weighted_total += w * mult
        cred_weighted_sev = weighted_total / n
    else:
        cred_weighted_sev = 0.0

    # ── price_anomaly_ratio ───────────────────────────────────────────────────
    if products:
        anomalous = sum(1 for p in products if p.price < PRICE_ANOMALY_RATIO * p.market_price)
        price_anom_ratio = anomalous / len(products)
    else:
        price_anom_ratio = 0.0
    has_price_anomaly = price_anom_ratio > 0.5

    # ── complaint frequency and age penalty ───────────────────────────────────
    age_days = max(1, seller.account_age_days)
    freq = total / max(1.0, age_days / 30.0)
    freq = min(5.0, freq)

    age_penalty = max(0.0, 0.5 * (1.0 - seller.account_age_days / NEW_ACCOUNT_DAYS)) \
        if seller.account_age_days < NEW_ACCOUNT_DAYS else 0.0

    # ── open_complaint_ratio ──────────────────────────────────────────────────
    open_ratio = min(1.0, len(open_complaints) / max(1, total))

    # ── data confidence factor for complaint-based signals ────────────────────
    data_confidence = min(1.0, total / 3.0)

    # ── Normalise each feature to [0, 1] ──────────────────────────────────────
    features: dict[str, float] = {
        "open_complaint_ratio":           min(1.0, open_ratio * data_confidence),
        "avg_severity":                   min(1.0, (avg_sev / 5.0) * data_confidence),
        "mean_visual_mismatch":           min(1.0, mean_mismatch * data_confidence),
        "buyer_credibility_weighted_sev": min(1.0, (cred_weighted_sev / 5.0) * data_confidence),
        "price_anomaly_ratio":            min(1.0, price_anom_ratio),
        "complaint_frequency":            min(1.0, freq / 5.0),
        "account_age_penalty":            age_penalty,
    }

    signals = SellerSignals(
        open_complaints=len(open_complaints),
        total_complaints=total,
        avg_severity=round(avg_sev, 3),
        mean_visual_mismatch=round(mean_mismatch, 4),
        buyer_credibility_weighted_sev=round(cred_weighted_sev, 3),
        price_anomaly_ratio=round(price_anom_ratio, 4),
        complaint_frequency=round(freq, 4),
        account_age_days=seller.account_age_days,
        account_age_penalty=round(age_penalty, 4),
        has_price_anomaly=has_price_anomaly,
        features=features,
    )

    return features, signals


def _features_to_trust_score(
    features: dict[str, float],
    signals: SellerSignals,
    previous_trust_score: Optional[int] = None,
    alpha: float = 0.3,
) -> int:
    """
    Apply FEATURE_WEIGHTS to the normalised feature vector to produce a
    weighted risk score, then convert to a trust score in [0, 100].

    For persistence, enable optional exponential smoothing using previous
    trust score to avoid abrupt trust jumps.
    """
    weighted_risk = sum(
        features.get(k, 0.0) * w
        for k, w in FEATURE_WEIGHTS.items()
    )
    # weighted_risk is already [0,1] since features are [0,1] and weights sum to 1.0
    signals.weighted_risk = round(weighted_risk, 4)
    new_raw = (1.0 - weighted_risk) * 100.0
    if previous_trust_score is None:
        trust_score = round(new_raw)
    else:
        prior = float(previous_trust_score or 100)
        smoothed = (1.0 - alpha) * prior + alpha * new_raw
        trust_score = int(round(smoothed))
    trust_score = max(0, min(100, trust_score))
    return trust_score


# ── Price anomaly helper (public) ─────────────────────────────────────────────

def has_price_anomaly(products: list[Product]) -> bool:
    if not products:
        return False
    anomalous = sum(1 for p in products if p.price < PRICE_ANOMALY_RATIO * p.market_price)
    return anomalous > len(products) / 2


# ── Public API ────────────────────────────────────────────────────────────────

def recalculate_trust_score(db: Session, seller_id: int) -> int:
    """
    Layer 1 — Historical Trust Score.

    Uses ALL complaints (open + resolved with decay).
    Persists the result to seller.trust_score.
    Does NOT commit — caller owns the transaction.

    Returns new trust_score, or -1 if seller not found.
    """
    seller = db.query(Seller).filter(Seller.id == seller_id).first()
    if seller is None:
        logger.warning("recalculate_trust_score: seller %d not found", seller_id)
        return -1

    complaints = db.query(Complaint).filter(Complaint.seller_id == seller_id).all()
    products   = db.query(Product).filter(Product.seller_id == seller_id).all()

    features, signals = _compute_features(seller, complaints, products, open_only=False)
    new_score = _features_to_trust_score(
        features,
        signals,
        previous_trust_score=seller.trust_score,
    )

    seller.trust_score = new_score
    logger.debug(
        "Seller %d recalculated: features=%s weighted_risk=%.4f score=%d",
        seller_id, features, signals.weighted_risk, new_score,
    )
    return new_score


def evaluate_current_risk(db: Session, seller_id: int) -> Optional[dict]:
    """
    Layer 2 — Real-Time Advisory Evaluation (read-only).

    Uses ONLY open complaints.
    Returns a dict including the full SellerSignals for the advisory/explainability layer.
    Returns None if seller not found.
    """
    seller = db.query(Seller).filter(Seller.id == seller_id).first()
    if seller is None:
        return None

    complaints = db.query(Complaint).filter(Complaint.seller_id == seller_id).all()
    products   = db.query(Product).filter(Product.seller_id == seller_id).all()

    features, signals = _compute_features(seller, complaints, products, open_only=True)
    fresh_score = _features_to_trust_score(features, signals, previous_trust_score=None)

    return {
        "seller":           seller,
        "fresh_trust_score":fresh_score,
        "open_complaints":  signals.open_complaints,
        "products":         products,
        "price_anomaly":    signals.has_price_anomaly,
        "signals":          signals,
    }
