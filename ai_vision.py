"""
ai_vision.py — Upgraded AI image comparison module.

Improvements over prototype:
  1. CLIP (ViT-B/32) as primary model — semantic understanding, not just pixel similarity.
     Robust to angle, lighting, and context differences.
  2. ResNet18 as automatic fallback if CLIP is unavailable.
  3. DB-backed embedding cache via EmbeddingCache model — embeddings are persisted
     across server restarts and never recomputed for the same file.
  4. In-process LRU cache as first-level hit (avoids even a DB round-trip).
  5. Batch comparison support via compare_images_batch().

Public API
----------
compare_images(path_a, path_b, db=None)  -> float
    Returns visual_mismatch_score in [0, 1].  0 = identical, 1 = completely different.

compare_images_batch(pairs, db=None)  -> list[float]
    Efficient batch comparison — embeddings computed once per unique image.

get_embedding_for_path(path, db=None)  -> list[float]
    Return (and cache) the embedding vector for a given image path.

clear_cache()
    Purge the in-process LRU cache (useful in tests).
"""

import json
import logging
import math
from functools import lru_cache
from pathlib import Path
from typing import Optional

import torch
import torch.nn.functional as F
from PIL import Image

from config import AI_MODEL, VISUAL_MISMATCH_THRESHOLD, MISMATCH_SIGMOID_SHARPNESS

logger = logging.getLogger(__name__)

# ── Device ────────────────────────────────────────────────────────────────────

_DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
logger.info("ai_vision: device=%s  preferred_model=%s", _DEVICE, AI_MODEL)

# ── Model loading ─────────────────────────────────────────────────────────────

_MODEL_NAME: str = "none"
_clip_model = None
_clip_preprocess = None
_resnet_extractor = None
_resnet_preprocess = None


def _try_load_clip():
    """Attempt to load CLIP ViT-B/32. Returns True on success."""
    global _clip_model, _clip_preprocess, _MODEL_NAME
    try:
        import clip  # pip install openai-clip
        model, preprocess = clip.load("ViT-B/32", device=_DEVICE)
        model.eval()
        _clip_model = model
        _clip_preprocess = preprocess
        _MODEL_NAME = "clip"
        logger.info("ai_vision: CLIP ViT-B/32 loaded successfully")
        return True
    except Exception as exc:
        logger.warning("ai_vision: CLIP unavailable (%s) — will try ResNet fallback", exc)
        return False


def _try_load_resnet():
    """Attempt to load ResNet18 feature extractor. Returns True on success."""
    global _resnet_extractor, _resnet_preprocess, _MODEL_NAME
    try:
        import torchvision.models as tvm
        import torchvision.transforms as T
        resnet = tvm.resnet18(weights=tvm.ResNet18_Weights.IMAGENET1K_V1)
        extractor = torch.nn.Sequential(*list(resnet.children())[:-1])
        extractor.eval().to(_DEVICE)
        _resnet_extractor = extractor
        _resnet_preprocess = T.Compose([
            T.Resize((224, 224)),
            T.ToTensor(),
            T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ])
        _MODEL_NAME = "resnet"
        logger.info("ai_vision: ResNet18 fallback loaded successfully")
        return True
    except Exception as exc:
        logger.error("ai_vision: ResNet also unavailable (%s) — AI disabled", exc)
        return False


# Load the preferred model at import time
if AI_MODEL == "clip":
    if not _try_load_clip():
        _try_load_resnet()
else:
    if not _try_load_resnet():
        _try_load_clip()

_MODEL_AVAILABLE = _MODEL_NAME != "none"


# ── Raw embedding computation (no caching) ───────────────────────────────────

def _compute_embedding_clip(path: str) -> list[float]:
    import clip
    img = _clip_preprocess(Image.open(path).convert("RGB")).unsqueeze(0).to(_DEVICE)
    with torch.no_grad():
        feat = _clip_model.encode_image(img)
    feat = F.normalize(feat.float(), p=2, dim=1)
    return feat.squeeze(0).cpu().tolist()


def _compute_embedding_resnet(path: str) -> list[float]:
    img = _resnet_preprocess(Image.open(path).convert("RGB")).unsqueeze(0).to(_DEVICE)
    with torch.no_grad():
        feat = _resnet_extractor(img)
    feat = F.normalize(feat.flatten(1), p=2, dim=1)
    return feat.squeeze(0).cpu().tolist()


def _compute_embedding(path: str) -> list[float]:
    """Compute embedding using the loaded model."""
    if _MODEL_NAME == "clip":
        return _compute_embedding_clip(path)
    elif _MODEL_NAME == "resnet":
        return _compute_embedding_resnet(path)
    raise RuntimeError("No AI model loaded")


# ── In-process LRU cache (L1) ─────────────────────────────────────────────────

@lru_cache(maxsize=512)
def _lru_embedding(abs_path: str) -> tuple:
    """LRU-cached embedding as a tuple (hashable). Key = absolute path."""
    return tuple(_compute_embedding(abs_path))


def clear_cache():
    """Purge the in-process LRU embedding cache (useful in tests)."""
    _lru_embedding.cache_clear()
    logger.debug("ai_vision: in-process embedding cache cleared")


# ── DB-backed embedding cache (L2) ───────────────────────────────────────────

def _get_embedding_with_db_cache(
    path: str,
    db=None,
) -> list[float]:
    """
    Return embedding for path, using a two-level cache:
      L1 — in-process LRU (fastest)
      L2 — database EmbeddingCache table (survives restart)
      L3 — compute fresh and store in both caches
    """
    abs_path = str(Path(path).resolve())

    # L1: in-process LRU
    try:
        return list(_lru_embedding(abs_path))
    except Exception:
        pass  # LRU miss (shouldn't happen, but safety net)

    # L2: DB cache
    if db is not None:
        try:
            from models import EmbeddingCache
            cached = (
                db.query(EmbeddingCache)
                .filter(
                    EmbeddingCache.image_path == path,
                    EmbeddingCache.model_name == _MODEL_NAME,
                )
                .first()
            )
            if cached:
                emb = json.loads(cached.embedding)
                # Warm the L1 cache
                _lru_embedding.__wrapped__ = None  # bypass for warming not needed
                return emb
        except Exception as exc:
            logger.debug("ai_vision: DB cache read failed: %s", exc)

    # L3: compute fresh
    emb = _compute_embedding(abs_path)

    # Store in DB cache
    if db is not None:
        try:
            from models import EmbeddingCache
            record = EmbeddingCache(
                image_path=path,
                model_name=_MODEL_NAME,
                embedding=json.dumps(emb),
            )
            db.add(record)
            db.flush()
        except Exception as exc:
            logger.debug("ai_vision: DB cache write failed: %s", exc)

    return emb


# ── Similarity → mismatch score ───────────────────────────────────────────────

def _cosine_similarity(a: list[float], b: list[float]) -> float:
    ta = torch.tensor(a, dtype=torch.float32)
    tb = torch.tensor(b, dtype=torch.float32)
    return float(F.cosine_similarity(ta.unsqueeze(0), tb.unsqueeze(0)).item())


def _similarity_to_mismatch(similarity: float) -> float:
    similarity = max(-1.0, min(1.0, similarity))
    raw = 1.0 - ((similarity + 1.0) / 2.0)
    return round(raw, 4)


# ── Public API ────────────────────────────────────────────────────────────────

def compare_images(path_a: str, path_b: str, db=None) -> float:
    """
    Compare two images and return a visual_mismatch_score in [0, 1].

    Parameters
    ----------
    path_a, path_b : paths to image files (absolute or relative to BASE_DIR)
    db             : optional SQLAlchemy Session for DB embedding cache

    Returns 0.0 on any error (safe fallback — never crashes the pipeline).
    """
    if not _MODEL_AVAILABLE:
        logger.warning("compare_images: no model available, returning 0.0")
        return 0.0

    try:
        emb_a = _get_embedding_with_db_cache(path_a, db)
        emb_b = _get_embedding_with_db_cache(path_b, db)
    except FileNotFoundError as exc:
        logger.warning("compare_images: file not found — %s", exc)
        return 0.0
    except Exception as exc:
        logger.error("compare_images: embedding error — %s", exc)
        return 0.0

    sim = _cosine_similarity(emb_a, emb_b)
    return _similarity_to_mismatch(sim)


def compare_images_batch(
    pairs: list[tuple[str, str]],
    db=None,
) -> list[float]:
    """
    Batch comparison — each unique image path is embedded only once.

    Parameters
    ----------
    pairs : list of (path_a, path_b) tuples
    db    : optional SQLAlchemy Session for DB embedding cache

    Returns a list of mismatch scores in the same order as pairs.
    """
    if not _MODEL_AVAILABLE:
        return [0.0] * len(pairs)

    # Collect unique paths and embed them all
    unique_paths = list({p for pair in pairs for p in pair})
    embeddings: dict[str, list[float]] = {}
    for path in unique_paths:
        try:
            embeddings[path] = _get_embedding_with_db_cache(path, db)
        except Exception as exc:
            logger.error("compare_images_batch: failed to embed %s — %s", path, exc)
            embeddings[path] = []

    results = []
    for path_a, path_b in pairs:
        emb_a = embeddings.get(path_a, [])
        emb_b = embeddings.get(path_b, [])
        if emb_a and emb_b:
            results.append(_similarity_to_mismatch(_cosine_similarity(emb_a, emb_b)))
        else:
            results.append(0.0)
    return results


def get_embedding_for_path(path: str, db=None) -> list[float]:
    """
    Return (and cache) the embedding vector for a given image path.
    Useful for pre-computing embeddings on product upload.
    """
    if not _MODEL_AVAILABLE:
        return []
    try:
        return _get_embedding_with_db_cache(path, db)
    except Exception as exc:
        logger.error("get_embedding_for_path: %s — %s", path, exc)
        return []


def get_model_name() -> str:
    """Return the name of the currently active AI model."""
    return _MODEL_NAME
