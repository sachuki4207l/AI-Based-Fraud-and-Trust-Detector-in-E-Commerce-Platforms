"""
text_analyzer.py — Text-based severity signal extraction.

Analyzes complaint text to compute a severity contribution (0-5).
Used by the auto-severity engine so users no longer set severity manually.
"""

import logging
import re

from config import SEVERITY_KEYWORDS

logger = logging.getLogger(__name__)


def extract_text_severity(complaint_text: str) -> int:
    """
    Scan complaint text for severity-indicating keywords and return a
    severity contribution integer in [0, 5].

    Algorithm:
    - Tokenise to lowercase, check each keyword.
    - Accumulate keyword scores, cap at 5.
    - Returns 1 as a minimum for any non-empty complaint text.
    """
    if not complaint_text or not complaint_text.strip():
        return 1

    text_lower = complaint_text.lower()
    total = 0

    for keyword, weight in SEVERITY_KEYWORDS.items():
        if keyword in text_lower:
            total += weight

    # Minimum 1 for any complaint, cap at 5
    return max(1, min(5, total))


def compute_auto_severity(
    mismatch_score: float,
    complaint_text: str,
    has_price_anomaly: bool = False,
) -> int:
    """
    Compute the final auto-determined severity level (1–5) by combining:
      1. AI visual mismatch score  (0.0–1.0)
      2. Text keyword analysis
      3. Price anomaly signal

    Weighting:
      - mismatch_score contributes up to 3 severity points
      - text_severity contributes up to 2 severity points (scaled down)
      - price anomaly adds +1 if present

    Final value is clamped to [1, 5].
    """
    # AI contribution: mismatch_score [0,1] → 0–3 points
    ai_contribution = round(mismatch_score * 3)

    # Text contribution: raw score [0–5] → scaled to 0–2
    text_raw = extract_text_severity(complaint_text)
    text_contribution = round((text_raw / 5.0) * 2)

    # Price anomaly signal: +1
    price_contribution = 1 if has_price_anomaly else 0

    raw = ai_contribution + text_contribution + price_contribution
    severity = max(1, min(5, raw))

    logger.debug(
        "auto_severity: mismatch=%.3f → ai=%d  text=%d  price=%d  final=%d",
        mismatch_score, ai_contribution, text_contribution, price_contribution, severity,
    )
    return severity
