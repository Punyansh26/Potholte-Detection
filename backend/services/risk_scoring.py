"""Risk scoring and severity classification.

score = severity_weight × 40 + confidence × 20 + exposure_factor × 40

If score ≥ threshold (default 80) → auto‑file grievance.
"""

from __future__ import annotations
from typing import List


def estimate_severity(bbox: List[float], image_width: int = 640, image_height: int = 480) -> str:
    """Estimate severity from bounding‑box area relative to frame size."""
    if len(bbox) < 4:
        return "low"
    x_min, y_min, x_max, y_max = bbox[:4]
    area = abs(x_max - x_min) * abs(y_max - y_min)
    frame_area = image_width * image_height
    ratio = area / frame_area if frame_area else 0

    if ratio > 0.15:
        return "critical"
    if ratio > 0.08:
        return "high"
    if ratio > 0.03:
        return "medium"
    return "low"


_SEVERITY_WEIGHTS = {"low": 0.2, "medium": 0.5, "high": 0.75, "critical": 1.0}


def compute_risk_score(
    severity: str,
    confidence: float = 0.5,
    exposure_factor: float = 0.5,
) -> float:
    """Return a 0–100 risk score."""
    sw = _SEVERITY_WEIGHTS.get(severity, 0.2)
    score = sw * 40 + confidence * 20 + exposure_factor * 40
    return round(min(max(score, 0), 100), 1)
