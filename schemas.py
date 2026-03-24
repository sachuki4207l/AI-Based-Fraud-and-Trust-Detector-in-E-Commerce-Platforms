"""
schemas.py — All Pydantic request/response models.

Every schema is annotated with Field() descriptions so Swagger /docs shows
human-readable labels, defaults, and constraints instead of raw field names.
Enums replace free-text strings so Swagger renders dropdowns.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ── Enums (render as Swagger dropdowns) ──────────────────────────────────────

class ComplaintStatus(str, Enum):
    open     = "open"
    resolved = "resolved"


class AdminStatus(str, Enum):
    pending  = "pending"
    approved = "approved"
    rejected = "rejected"
    spam     = "spam"


class ProcessingStatus(str, Enum):
    queued = "queued"
    done   = "done"


class AdminAction(str, Enum):
    approve = "approve"
    reject  = "reject"
    spam    = "spam"


# ── Seller ────────────────────────────────────────────────────────────────────

class SellerCreate(BaseModel):
    name: str = Field(
        ...,
        min_length=1,
        max_length=120,
        description="Display name of the seller",
        examples=["TechZone Store"],
    )
    account_age_days: int = Field(
        default=365,
        ge=0,
        description="How many days the seller account has been active (0 = brand new)",
        examples=[365],
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "name": "TechZone Store",
                    "account_age_days": 365,
                }
            ]
        }
    }


class SellerOut(BaseModel):
    id:               int   = Field(..., description="Unique seller ID")
    name:             str   = Field(..., description="Seller display name")
    account_age_days: int   = Field(..., description="Account age in days")
    trust_score:      int   = Field(..., description="Current trust score (0–100). ≥70 Safe, 40–69 Caution, <40 High Risk")

    model_config = {"from_attributes": True}


# ── Buyer ─────────────────────────────────────────────────────────────────────

class BuyerCreate(BaseModel):
    name: str = Field(
        ...,
        min_length=1,
        max_length=120,
        description="Display name of the buyer",
        examples=["Alice Johnson"],
    )

    model_config = {
        "json_schema_extra": {
            "examples": [{"name": "Alice Johnson"}]
        }
    }


class BuyerOut(BaseModel):
    id:                int = Field(..., description="Unique buyer ID")
    name:              str = Field(..., description="Buyer display name")
    credibility_score: int = Field(..., description="Credibility score (20–100). Higher = complaints carry more weight against sellers")
    spam_flag_count:   int = Field(..., description="Number of times this buyer's complaints were marked spam by admin")

    model_config = {"from_attributes": True}


# ── Product ───────────────────────────────────────────────────────────────────

class ProductOut(BaseModel):
    id:           int   = Field(..., description="Unique product ID")
    title:        str   = Field(..., description="Product title as listed")
    price:        float = Field(..., description="Listed selling price in USD")
    market_price: float = Field(..., description="Typical market price (used for anomaly detection)")
    seller_id:    int   = Field(..., description="ID of the seller who listed this product")
    image_path:   str   = Field(..., description="Relative path to product image, e.g. uploads/products/abc.jpg")

    model_config = {"from_attributes": True}


# ── Complaint ─────────────────────────────────────────────────────────────────

class ComplaintOut(BaseModel):
    id:                   int                      = Field(..., description="Unique complaint ID")
    buyer_id:             int                      = Field(..., description="ID of the buyer who filed this complaint")
    seller_id:            int                      = Field(..., description="ID of the seller being complained about")
    product_id:           int                      = Field(..., description="ID of the product in question")
    complaint_text:       str                      = Field(..., description="Buyer's description of the issue")
    severity_level:       int                      = Field(..., description="Auto-computed severity 1–5 (0 = still processing). 1=Minor, 3=Moderate, 5=Critical")
    status:               ComplaintStatus          = Field(..., description="Complaint lifecycle status")
    admin_status:         AdminStatus              = Field(..., description="Admin review status")
    processing_status:    ProcessingStatus         = Field(..., description="AI processing pipeline status. Poll until 'done' for final severity and mismatch score")
    received_image_path:  Optional[str]            = Field(None, description="Path to buyer's evidence image, if uploaded")
    visual_mismatch_score:float                    = Field(..., description="AI-computed image mismatch confidence 0.0–1.0. 0=identical, 1=completely different. Set after processing completes")
    created_at:           datetime                 = Field(..., description="When the complaint was submitted (UTC)")
    updated_at:           datetime                 = Field(..., description="Last modification timestamp (UTC)")

    model_config = {"from_attributes": True}


class ComplaintCreateResponse(BaseModel):
    """Returned immediately after complaint submission (before AI processing completes)."""
    complaint_id:      int              = Field(..., description="ID to use for polling GET /complaints/{id}")
    processing_status: ProcessingStatus = Field(..., description="Will be 'queued' immediately. Poll until 'done'")
    message:           str              = Field(..., description="Human-readable status message")
    complaint:         ComplaintOut     = Field(..., description="Full complaint object with initial values")


class ComplaintUpdate(BaseModel):
    """Update a complaint's text or resolve it. Severity is system-managed."""
    complaint_id:   int                       = Field(..., gt=0, description="ID of the complaint to update", examples=[1])
    complaint_text: Optional[str]             = Field(None, min_length=1, description="Updated complaint description (optional)")
    status:         Optional[ComplaintStatus] = Field(None, description="Set to 'resolved' to close the complaint")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"complaint_id": 1, "status": "resolved"},
                {"complaint_id": 1, "complaint_text": "The product was a different colour than advertised"},
            ]
        }
    }

    @model_validator(mode="after")
    def at_least_one_field(self):
        if self.complaint_text is None and self.status is None:
            raise ValueError("At least one of complaint_text or status must be provided")
        return self


# ── Admin ─────────────────────────────────────────────────────────────────────

class AdminActionRequest(BaseModel):
    """Body for admin approve/reject/spam — used by the combined action endpoint."""
    action: AdminAction = Field(
        ...,
        description="approve = valid complaint (buyer rewarded), reject = invalid (buyer penalised), spam = fraudulent (buyer heavily penalised)",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [{"action": "approve"}]
        }
    }


# Keep old name for backward compatibility
AdminComplaintAction = AdminActionRequest


class AdminActionResponse(BaseModel):
    """Rich response after an admin action — shows all downstream effects."""
    complaint:              ComplaintOut = Field(..., description="Updated complaint with new admin_status")
    buyer_credibility_after:int          = Field(..., description="Buyer's credibility score after adjustment")
    seller_trust_after:     int          = Field(..., description="Seller's trust score after recalculation")
    action_taken:           str          = Field(..., description="Which action was applied")
    credibility_change:     int          = Field(..., description="Net change to buyer credibility (+positive, -negative)")


class RecalculateResponse(BaseModel):
    seller_id:   int = Field(..., description="Seller ID that was recalculated")
    trust_score: int = Field(..., description="Newly computed trust score (0–100)")
    message:     str = Field(..., description="Confirmation message")


# ── Advisory ─────────────────────────────────────────────────────────────────

class SignalsOut(BaseModel):
    """
    Complete feature vector used to compute trust score.
    Every value is normalized to 0–1 before being multiplied by its weight.
    weighted_risk = sum of (feature × weight). trust_score = (1 - weighted_risk) × 100.
    """
    open_complaints:               int   = Field(..., description="Number of currently open complaints against this seller")
    total_complaints:              int   = Field(..., description="All-time complaint count (open + resolved)")
    avg_severity:                  float = Field(..., description="Mean severity of open complaints (0–5 scale)")
    mean_visual_mismatch:          float = Field(..., description="Average AI visual mismatch score across open complaints (0.0–1.0)")
    buyer_credibility_weighted_sev:float = Field(..., description="Severity re-weighted by buyer credibility — low-credibility buyers reduce impact")
    price_anomaly_ratio:           float = Field(..., description="Fraction of products priced suspiciously below market (0.0–1.0). >0.5 triggers anomaly flag")
    complaint_frequency:           float = Field(..., description="Complaints per 30-day period relative to account age")
    account_age_days:              int   = Field(..., description="Seller account age in days")
    has_price_anomaly:             bool  = Field(..., description="True if >50% of seller's products are priced below 60% of market price")
    weighted_risk:                 float = Field(..., description="Final weighted risk score (0.0–1.0). trust_score = (1 - weighted_risk) × 100")


class AdvisoryOut(BaseModel):
    """Full trust advisory response — powers the purchase recommendation system."""
    seller_id:            int        = Field(..., description="Seller being evaluated")
    seller_name:          str        = Field(..., description="Seller display name")
    trust_score:          int        = Field(..., description="Real-time trust score (0–100). Uses open complaints only — resolving complaints improves this immediately")
    risk_level:           str        = Field(..., description="Safe (≥70) | Caution (40–69) | High Risk (<40)")
    recommendation:       str        = Field(..., description="Human-readable purchase recommendation")
    reasons:              list[str]  = Field(..., description="Ordered list of risk factors from most to least important")
    signals:              SignalsOut = Field(..., description="Full feature vector — shows exactly what drove the trust score")
    open_complaint_count: int        = Field(..., description="Number of unresolved complaints")
    has_price_anomaly:    bool       = Field(..., description="Whether the seller has suspicious pricing patterns")
    account_age_days:     int        = Field(..., description="Seller account age in days")
    ai_model_used:        str        = Field(..., description="Which AI model computed the visual mismatch scores (clip | resnet | none)")
