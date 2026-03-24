"""
config.py — Centralised application settings and constants.
All tuneable parameters live here.
"""

import os
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────

BASE_DIR: Path = Path(__file__).resolve().parent

# ── Database ──────────────────────────────────────────────────────────────────
# Set DATABASE_URL env var to a PostgreSQL DSN for production:
#   postgresql+psycopg2://user:password@host:5432/dbname
DATABASE_URL: str = os.environ.get(
    "DATABASE_URL",
    f"sqlite:///{BASE_DIR / 'fraud_detection.db'}",
)

UPLOAD_DIR_PRODUCTS: Path = BASE_DIR / "uploads" / "products"
UPLOAD_DIR_COMPLAINTS: Path = BASE_DIR / "uploads" / "complaints"
EMBEDDING_CACHE_DIR: Path = BASE_DIR / "uploads" / "embeddings"

UPLOAD_DIR_PRODUCTS.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR_COMPLAINTS.mkdir(parents=True, exist_ok=True)
EMBEDDING_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# ── Upload validation ─────────────────────────────────────────────────────────

ALLOWED_IMAGE_EXTENSIONS: frozenset[str] = frozenset({"jpg", "jpeg", "png", "webp"})
MAX_IMAGE_SIZE_BYTES: int = 5 * 1024 * 1024  # 5 MB

# ── AI Model selection ────────────────────────────────────────────────────────
# "clip"   -> use CLIP ViT-B/32 (preferred, semantic understanding)
# "resnet" -> use ResNet18 feature extractor (fallback)
AI_MODEL: str = os.environ.get("AI_MODEL", "clip")

VISUAL_MISMATCH_THRESHOLD = 0.25
MISMATCH_SIGMOID_SHARPNESS = 4.0

# ── Auto-severity: users NO LONGER supply severity; system computes it ────────

# Keyword severity boosts for complaint text (case-insensitive)
SEVERITY_KEYWORDS: dict[str, int] = {
    "fraud":       3,
    "fake":        3,
    "scam":        3,
    "counterfeit": 3,
    "wrong":       2,
    "broken":      2,
    "damaged":     2,
    "missing":     2,
    "different":   1,
    "poor":        1,
    "bad":         1,
    "not working": 2,
    "defective":   2,
}

# ── Feature-driven trust scoring weights ─────────────────────────────────────
# Each feature is normalised to [0,1] before weighting.
FEATURE_WEIGHTS: dict[str, float] = {
    "open_complaint_ratio":           0.25,
    "avg_severity":                   0.20,
    "mean_visual_mismatch":           0.20,
    "buyer_credibility_weighted_sev": 0.15,
    "price_anomaly_ratio":            0.10,
    "complaint_frequency":            0.05,
    "account_age_penalty":            0.05,
}

# ── Legacy fraud-engine constants (kept for internal helpers) ─────────────────

SEVERITY_WEIGHTS: dict[int, float] = {1: 2.0, 2: 5.0, 3: 10.0, 4: 20.0, 5: 35.0}
RESOLVED_DECAY_FACTOR: float = 0.20
VISUAL_MISMATCH_RISK_PER_COMPLAINT: float = 8.0
MAX_COUNT_RISK: int = 40
NEW_ACCOUNT_DAYS: int = 30
PRICE_ANOMALY_RATIO: float = 0.60

# ── Advisory thresholds ───────────────────────────────────────────────────────

SAFE_THRESHOLD: int = 70
CAUTION_THRESHOLD: int = 40

# ── Buyer credibility ─────────────────────────────────────────────────────────

BUYER_CREDIBILITY_MIN: int = 20
BUYER_CREDIBILITY_MAX: int = 100
COMPLAINT_SUBMISSION_PENALTY: int = 2
RESOLUTION_PENALTY: int = 3
RESOLUTION_REWARD_LOW_SEV: int = 1
VALID_COMPLAINT_REWARD: int = 5    # admin approves complaint -> buyer gains this
SPAM_COMPLAINT_PENALTY: int = 8    # admin rejects as spam -> buyer loses this
