"""
models.py — SQLAlchemy ORM models.

New in this version:
  - EmbeddingCache table: persists image embeddings so CLIP/ResNet never
    re-processes the same image file twice.
  - Complaint.admin_status: "pending" | "approved" | "rejected" | "spam"
    supports the new admin control layer.
  - Complaint.severity_level no longer supplied by users; computed by system.
  - Complaint.processing_status: "queued" | "done" for async pipeline.
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Column, Float, Integer, String, DateTime,
    ForeignKey, UniqueConstraint, Index, Text,
)
from sqlalchemy.orm import relationship

from database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── Seller ────────────────────────────────────────────────────────────────────

class Seller(Base):
    __tablename__ = "sellers"

    id                = Column(Integer, primary_key=True, index=True)
    name              = Column(String, nullable=False)
    account_age_days  = Column(Integer, nullable=False, default=0)
    trust_score       = Column(Integer, nullable=False, default=100)

    products   = relationship("Product",   back_populates="seller", lazy="select")
    complaints = relationship("Complaint", back_populates="seller", lazy="select")

    def __repr__(self):
        return f"<Seller id={self.id} name={self.name!r} trust={self.trust_score}>"


# ── Buyer ─────────────────────────────────────────────────────────────────────

class Buyer(Base):
    __tablename__ = "buyers"

    id                = Column(Integer, primary_key=True, index=True)
    name              = Column(String, nullable=False)
    credibility_score = Column(Integer, nullable=False, default=100)
    spam_flag_count   = Column(Integer, nullable=False, default=0)

    complaints = relationship("Complaint", back_populates="buyer", lazy="select")

    def __repr__(self):
        return f"<Buyer id={self.id} name={self.name!r} cred={self.credibility_score}>"


# ── Product ───────────────────────────────────────────────────────────────────

class Product(Base):
    __tablename__ = "products"

    id           = Column(Integer, primary_key=True, index=True)
    title        = Column(String, nullable=False)
    price        = Column(Float, nullable=False)
    market_price = Column(Float, nullable=False)
    image_path   = Column(String, nullable=False, default="")
    seller_id    = Column(Integer, ForeignKey("sellers.id"), nullable=False, index=True)

    seller     = relationship("Seller",    back_populates="products")
    complaints = relationship("Complaint", back_populates="product", lazy="select")

    def __repr__(self):
        return f"<Product id={self.id} title={self.title!r} price={self.price}>"


# ── Complaint ─────────────────────────────────────────────────────────────────

class Complaint(Base):
    __tablename__ = "complaints"

    id         = Column(Integer, primary_key=True, index=True)
    buyer_id   = Column(Integer, ForeignKey("buyers.id"),    nullable=False, index=True)
    seller_id  = Column(Integer, ForeignKey("sellers.id"),   nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"),  nullable=False, index=True)

    complaint_text = Column(String, nullable=False)

    # Severity is now AUTO-COMPUTED by the system (not user-supplied).
    # Starts at 0 while async processing is queued; set by worker.
    severity_level = Column(Integer, nullable=False, default=0)

    # "open" | "resolved"
    status = Column(String, nullable=False, default="open")

    # NEW: admin review status — "pending" | "approved" | "rejected" | "spam"
    admin_status = Column(String, nullable=False, default="pending")

    # NEW: async pipeline tracking — "queued" | "done"
    processing_status = Column(String, nullable=False, default="queued")

    received_image_path   = Column(String, nullable=True)
    visual_mismatch_score = Column(Float,  nullable=False, default=0.0)

    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    buyer   = relationship("Buyer",   back_populates="complaints")
    seller  = relationship("Seller",  back_populates="complaints")
    product = relationship("Product", back_populates="complaints")

    __table_args__ = (
        UniqueConstraint("buyer_id", "product_id", name="uq_buyer_product"),
        Index("ix_complaints_seller_status", "seller_id", "status"),
        Index("ix_complaints_admin_status",  "admin_status"),
    )

    def __repr__(self):
        return (
            f"<Complaint id={self.id} seller={self.seller_id} "
            f"sev={self.severity_level} status={self.status!r} admin={self.admin_status!r}>"
        )


# ── EmbeddingCache ────────────────────────────────────────────────────────────

class EmbeddingCache(Base):
    """
    Persists image embeddings so AI models never re-process the same file.

    image_path : relative path used as the cache key (e.g. uploads/products/abc.jpg)
    model_name : "clip" | "resnet" — embeddings differ per model
    embedding  : JSON-serialised list of floats
    created_at : when the embedding was computed
    """
    __tablename__ = "embedding_cache"

    id         = Column(Integer, primary_key=True, index=True)
    image_path = Column(String, nullable=False, index=True)
    model_name = Column(String, nullable=False)
    embedding  = Column(Text, nullable=False)   # JSON array of floats
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    __table_args__ = (
        UniqueConstraint("image_path", "model_name", name="uq_embedding_path_model"),
    )

    def __repr__(self):
        return f"<EmbeddingCache path={self.image_path!r} model={self.model_name!r}>"
