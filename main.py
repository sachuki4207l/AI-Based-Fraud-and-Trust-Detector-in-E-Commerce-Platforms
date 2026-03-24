"""
main.py — FastAPI application entry point.
"""

import logging
import sys
from pathlib import Path
from contextlib import asynccontextmanager

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config import BASE_DIR
from database import engine, Base
from routes import sellers, products, buyers, complaints, advisory
from routes import admin as admin_routes

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Swagger tag groups (controls order and descriptions in /docs sidebar) ─────

TAGS_METADATA = [
    {
        "name": "1. Sellers",
        "description": """
**Manage seller accounts.**

Start here to create a seller. Every seller starts with `trust_score = 100`.
The score decreases automatically as complaints are filed and processed.

**Quick start:** `POST /sellers/add` → note the returned `id`.
""",
    },
    {
        "name": "2. Buyers",
        "description": """
**Manage buyer accounts.**

Buyers file complaints. Their `credibility_score` (20–100) determines how
much weight their complaints carry against sellers.

**Quick start:** `POST /buyers/add` → note the returned `id`.
""",
    },
    {
        "name": "3. Products",
        "description": """
**Manage product listings.**

Each product belongs to a seller. Price vs market_price comparison is used
for anomaly detection. Upload a product image — the AI will compare it to
complaint evidence images to detect mismatches.

**Quick start:** `POST /products/add` (requires seller_id) → note the returned `id`.
""",
    },
    {
        "name": "4. Complaints",
        "description": """
**File and track complaints.**

Complaints are non-blocking — submitted instantly and processed by the AI in the background.
The system auto-computes severity from image mismatch + keyword analysis + price signals.

**Workflow:**
1. `POST /complaints/add` → returns `complaint_id` immediately
2. `GET /complaints/{id}` → poll until `processing_status = "done"`
3. View final `severity_level` and `visual_mismatch_score`
""",
    },
    {
        "name": "5. Advisory",
        "description": """
**Real-time seller trust assessment.**

Returns trust score, risk level, purchase recommendation, risk reasons,
and the full feature vector (signals) that drove the score.

Use `GET /advisory/seller/{id}` at any point to get the current risk assessment.
""",
    },
    {
        "name": "6. Admin",
        "description": """
**Admin control panel — complaint review and seller monitoring.**

**Complaint actions (each updates buyer credibility + seller trust):**
- `PUT /admin/complaints/{id}/approve` → valid complaint, buyer +5 credibility
- `PUT /admin/complaints/{id}/reject`  → invalid complaint, buyer -3 credibility
- `PUT /admin/complaints/{id}/spam`    → fraudulent, buyer -8, spam_flag_count +1

**Seller tools:**
- `POST /admin/sellers/{id}/recalculate` → force trust score recalculation
- `GET /admin/sellers/suspicious` → list risky sellers
- `GET /admin/sellers/{id}/signals` → full feature vector debug breakdown
""",
    },
    {
        "name": "Health",
        "description": "System health check — shows active AI model, DB backend, and configured thresholds.",
    },
]


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info("Starting Fraud & Trust Detection API…")
    Base.metadata.create_all(bind=engine)
    from ai_vision import get_model_name
    logger.info("Active AI model: %s", get_model_name())
    yield
    logger.info("API shutting down.")


app = FastAPI(
    title="Fraud & Trust Detection API",
    description="""
# AI-Based Bidirectional Fraud & Trust Detection System

An AI-assisted trust intelligence platform for e-commerce marketplaces.
Combines visual AI evidence (CLIP/ResNet image comparison) with behavioral analytics
to generate explainable seller trust scores and purchase recommendations.

---

## Complete Workflow (use /docs as your control panel)

### Step 1 — Setup
```
POST /sellers/add     → Create a seller (note seller_id)
POST /buyers/add      → Create a buyer (note buyer_id)
POST /products/add    → Add a product with image (note product_id)
```

### Step 2 — Submit a complaint
```
POST /complaints/add  → File complaint (returns immediately with complaint_id)
GET  /complaints/{id} → Poll until processing_status = "done"
```

### Step 3 — Check trust impact
```
GET /advisory/seller/{seller_id}    → Full trust report with signals
GET /sellers/{seller_id}            → Updated trust_score
```

### Step 4 — Admin review
```
PUT /admin/complaints/{id}/approve  → Valid complaint → buyer +5 cred
PUT /admin/complaints/{id}/reject   → Invalid → buyer -3 cred
PUT /admin/complaints/{id}/spam     → Fraud → buyer -8 cred, spam+1
GET /admin/sellers/suspicious       → Monitor risky sellers
GET /admin/sellers/{id}/signals     → Debug trust score formula
```

---

## Trust Score Formula

`trust_score = (1 - weighted_risk) × 100`

Where `weighted_risk = Σ(normalised_feature × weight)`:

| Feature | Weight |
|---|---|
| open_complaint_ratio | 25% |
| avg_severity | 20% |
| mean_visual_mismatch | 20% |
| buyer_credibility_weighted_sev | 15% |
| price_anomaly_ratio | 10% |
| complaint_frequency | 5% |
| account_age_penalty | 5% |

**Risk levels:** ≥70 = Safe ✅ | 40–69 = Caution ⚠️ | <40 = High Risk 🚨

---

## AI Pipeline

1. Buyer uploads evidence image with complaint
2. CLIP (ViT-B/32) or ResNet18 generates 512-d embeddings
3. Cosine similarity computed between listing and evidence images
4. Sigmoid maps similarity → mismatch confidence score [0.0, 1.0]
5. Auto-severity = AI score (0–3 pts) + keyword analysis (0–2 pts) + price anomaly (0–1 pt)
""",
    version="3.0.0",
    openapi_tags=TAGS_METADATA,
    lifespan=lifespan,
    contact={
        "name": "TrustMart API",
    },
    license_info={
        "name": "College Project",
    },
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── API Routers ───────────────────────────────────────────────────────────────
app.include_router(sellers.router)
app.include_router(products.router)
app.include_router(buyers.router)
app.include_router(complaints.router)
app.include_router(advisory.router)
app.include_router(admin_routes.router)

# ── Static & uploads ──────────────────────────────────────────────────────────
app.mount("/static",  StaticFiles(directory=str(BASE_DIR / "static")),  name="static")
app.mount("/uploads", StaticFiles(directory=str(BASE_DIR / "uploads")), name="uploads")

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


# ── Frontend routes ───────────────────────────────────────────────────────────

@app.get("/", tags=["Frontend"], include_in_schema=False)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/product/{product_id}", tags=["Frontend"], include_in_schema=False)
def product_detail(request: Request, product_id: int):
    return templates.TemplateResponse("product_detail.html", {"request": request, "product_id": product_id})

@app.get("/seller/products", tags=["Frontend"], include_in_schema=False)
def seller_products(request: Request):
    """Seller: manage own product listings."""
    return templates.TemplateResponse("seller_products.html", {"request": request})

@app.get("/seller/{seller_id}", tags=["Frontend"], include_in_schema=False)
def seller_dashboard(request: Request, seller_id: int):
    return templates.TemplateResponse("seller_dashboard.html", {"request": request, "seller_id": seller_id})

@app.get("/seller-view/{seller_id}", tags=["Frontend"], include_in_schema=False)
def seller_view(request: Request, seller_id: int):
    return templates.TemplateResponse("seller_view.html", {"request": request, "seller_id": seller_id})

@app.get("/complaint/new", tags=["Frontend"], include_in_schema=False)
def complaint_form(request: Request, product_id: int = 0, seller_id: int = 0):
    return templates.TemplateResponse("complaint_form.html", {
        "request": request, "product_id": product_id, "seller_id": seller_id,
    })

@app.get("/complaint/{complaint_id}", tags=["Frontend"], include_in_schema=False)
def complaint_track(request: Request, complaint_id: int):
    return templates.TemplateResponse("complaint_track.html", {"request": request, "complaint_id": complaint_id})

@app.get("/admin-panel", tags=["Frontend"], include_in_schema=False)
def admin_panel(request: Request):
    return templates.TemplateResponse("admin_panel.html", {"request": request})

@app.get("/manage", tags=["Frontend"], include_in_schema=False)
def manage_panel(request: Request):
    """CRUD management panel — add, edit, delete sellers/buyers/products/complaints."""
    return templates.TemplateResponse("manage.html", {"request": request})

# ── Buyer role pages ──────────────────────────────────────────────────────────

@app.get("/my-complaints", tags=["Frontend"], include_in_schema=False)
def my_complaints(request: Request):
    """Buyer: view own complaint history."""
    return templates.TemplateResponse("my_complaints.html", {"request": request})

# ── Seller role pages ─────────────────────────────────────────────────────────


# ── Admin role pages ──────────────────────────────────────────────────────────

@app.get("/admin-complaints", tags=["Frontend"], include_in_schema=False)
def admin_complaints_page(request: Request):
    """Admin: complaint moderation queue."""
    return templates.TemplateResponse("admin_complaints.html", {"request": request})

@app.get("/admin-sellers", tags=["Frontend"], include_in_schema=False)
def admin_sellers_page(request: Request):
    """Admin: seller monitoring and trust overview."""
    return templates.TemplateResponse("admin_sellers.html", {"request": request})

@app.get("/admin/signals/{seller_id}", tags=["Frontend"], include_in_schema=False)
def admin_signals_page(request: Request, seller_id: int):
    """Admin: debug feature vector for a seller."""
    return templates.TemplateResponse("admin_signals.html", {"request": request, "seller_id": seller_id})

@app.get("/control-panel", tags=["Frontend"], include_in_schema=False)
def control_panel_page(request: Request):
    """Interactive API control panel."""
    return templates.TemplateResponse("control_panel.html", {"request": request})


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["Health"], summary="System health check")
def health_check():
    """Returns API status, active AI model, database backend, and configured trust thresholds."""
    from ai_vision import get_model_name
    from config import DATABASE_URL, FEATURE_WEIGHTS, SAFE_THRESHOLD, CAUTION_THRESHOLD
    return {
        "status":             "running",
        "version":            app.version,
        "ai_model":           get_model_name(),
        "db_backend":         "sqlite" if DATABASE_URL.startswith("sqlite") else "postgresql",
        "safe_threshold":     SAFE_THRESHOLD,
        "caution_threshold":  CAUTION_THRESHOLD,
        "feature_weights":    FEATURE_WEIGHTS,
        "docs_url":           "/docs",
        "redoc_url":          "/redoc",
    }
