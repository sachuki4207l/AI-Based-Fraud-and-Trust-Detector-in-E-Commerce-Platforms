# 🛡️ AI-Based Bidirectional Fraud & Trust Detection System

An AI-assisted trust intelligence platform for e-commerce marketplaces. Combines **visual AI evidence** (CLIP / ResNet image comparison) with **behavioral analytics** to generate explainable seller trust scores and purchase recommendations.

> Built with FastAPI · SQLAlchemy · PyTorch · CLIP ViT-B/32

---

## ✨ Key Features

- **AI-Powered Image Comparison** — CLIP ViT-B/32 (or ResNet18 fallback) compares product listing images with buyer-submitted evidence photos to detect visual mismatches
- **Auto-Severity Engine** — Complaints are automatically scored (1–5) based on AI mismatch, keyword analysis, and price anomaly signals
- **Bidirectional Trust Model** — Both sellers (trust score) and buyers (credibility score) are tracked and updated based on complaint outcomes
- **Feature-Driven Trust Scoring** — 7-dimensional weighted feature vector produces transparent, explainable trust scores
- **Non-Blocking Complaint Pipeline** — Complaints are submitted instantly; AI processing runs in the background
- **Admin Control Layer** — Approve, reject, or mark complaints as spam with automatic credibility adjustments
- **Full Web UI** — Admin panel, seller dashboard, complaint forms, and product management
- **Interactive API Docs** — Auto-generated Swagger UI at `/docs` and ReDoc at `/redoc`

---

## 🏗️ Architecture

```
Client Request
     │
     ▼
┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  FastAPI     │────▶│  SQLAlchemy ORM  │────▶│  SQLite / PgSQL  │
│  (Routes)   │     │  (Models)        │     │  (Database)      │
└──────┬──────┘     └──────────────────┘     └─────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────┐
│  Background Worker Pipeline                              │
│  ┌──────────┐  ┌───────────────┐  ┌──────────────────┐  │
│  │ AI Vision│─▶│ Text Analyzer │─▶│ Fraud Engine     │  │
│  │ (CLIP)   │  │ (Keywords)    │  │ (Trust Scoring)  │  │
│  └──────────┘  └───────────────┘  └──────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

---

## 🧮 Trust Score Formula

```
trust_score = (1 - weighted_risk) × 100
```

| Feature                        | Weight |
|--------------------------------|--------|
| `open_complaint_ratio`         | 25%    |
| `avg_severity`                 | 20%    |
| `mean_visual_mismatch`         | 20%    |
| `buyer_credibility_weighted_sev` | 15%  |
| `price_anomaly_ratio`          | 10%    |
| `complaint_frequency`          | 5%     |
| `account_age_penalty`          | 5%     |

**Risk levels:** ≥70 = Safe ✅ | 40–69 = Caution ⚠️ | <40 = High Risk 🚨

---

## 📁 Project Structure

```
role_build/
├── main.py              # FastAPI app entry point & frontend routes
├── config.py            # Centralised settings and constants
├── database.py          # SQLAlchemy engine & session factory
├── models.py            # ORM models (Seller, Buyer, Product, Complaint, EmbeddingCache)
├── schemas.py           # Pydantic request/response models
├── ai_vision.py         # CLIP/ResNet image comparison module
├── fraud_engine.py      # Feature-driven trust scoring engine
├── text_analyzer.py     # Text-based severity signal extraction
├── worker.py            # Background task processing pipeline
├── requirements.txt     # Python dependencies
│
├── routes/
│   ├── sellers.py       # Seller CRUD endpoints
│   ├── buyers.py        # Buyer CRUD endpoints
│   ├── products.py      # Product CRUD with image upload
│   ├── complaints.py    # Complaint lifecycle endpoints
│   ├── advisory.py      # Real-time trust advisory
│   └── admin.py         # Admin control layer
│
├── utils/
│   └── file_handler.py  # File upload validation & saving
│
├── templates/           # Jinja2 HTML templates (17 pages)
├── static/              # CSS, JS frontend assets
├── tests/               # Pytest test suite
└── uploads/             # Runtime image storage (git-ignored)
    ├── products/
    ├── complaints/
    └── embeddings/
```

---

## 🚀 Getting Started

### Prerequisites

- **Python 3.10+**
- **pip** (Python package manager)
- **Git**

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/<your-username>/role_build.git
   cd role_build
   ```

2. **Create a virtual environment** (recommended)
   ```bash
   python -m venv venv

   # Windows
   venv\Scripts\activate

   # macOS / Linux
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

   > **Note:** `torch` and `torchvision` are large packages (~2 GB). For CPU-only:
   > ```bash
   > pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
   > ```

4. **Run the application**
   ```bash
   uvicorn main:app --reload
   ```

5. **Open in browser**
   - Web UI: [http://127.0.0.1:8000](http://127.0.0.1:8000)
   - Swagger API Docs: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
   - ReDoc: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)

---

## ⚙️ Configuration

All settings are in `config.py` and can be overridden via environment variables:

| Variable       | Default   | Description                              |
|----------------|-----------|------------------------------------------|
| `DATABASE_URL` | SQLite    | Database connection string               |
| `AI_MODEL`     | `clip`    | AI model: `clip` or `resnet`             |

For PostgreSQL in production:
```bash
export DATABASE_URL="postgresql+psycopg2://user:password@host:5432/dbname"
pip install psycopg2-binary
```

---

## 🧪 Running Tests

```bash
python -m pytest tests/ -v
```

Tests use an in-memory SQLite database and are fully isolated.

---

## 📡 API Quick Start

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
GET /advisory/seller/{seller_id}  → Full trust report with signals
GET /sellers/{seller_id}          → Updated trust_score
```

### Step 4 — Admin review
```
PUT /admin/complaints/{id}/approve  → Valid complaint → buyer +5 cred
PUT /admin/complaints/{id}/reject   → Invalid → buyer -3 cred
PUT /admin/complaints/{id}/spam     → Fraud → buyer -8 cred
```

---

## 🛠️ Tech Stack

| Layer      | Technology                            |
|------------|---------------------------------------|
| Backend    | FastAPI, Uvicorn                      |
| Database   | SQLAlchemy ORM, SQLite / PostgreSQL   |
| AI Models  | CLIP ViT-B/32, ResNet18 (PyTorch)    |
| Validation | Pydantic v2                           |
| Templates  | Jinja2                                |
| Frontend   | HTML, CSS, JavaScript                 |
| Testing    | Pytest, HTTPX                         |

---

## 📄 License

This project was developed as a college project.
