"""Synthetic ultrasonic telemetry for hackathon sensor-fusion demos."""

from __future__ import annotations

import random
from typing import Any


_SEVERITY_MIN_DEPTH_CM = {
    "low": 2.5,
    "medium": 5.5,
    "high": 9.0,
    "critical": 13.0,
}


def synthesize_ultrasonic_profile(
    bbox: list[int] | list[float],
    frame_w: int,
    frame_h: int,
    confidence: float,
    severity: str,
) -> dict[str, Any]:
    """Return deterministic ultrasonic demo telemetry for a detected pothole.

    Values simulate a down-facing ultrasonic sensor mounted on a vehicle body.
    Higher/deeper potholes produce lower distance-to-road readings and higher
    estimated pothole depth.
    """
    if len(bbox) < 4 or frame_w <= 0 or frame_h <= 0:
        return {
            "ultrasonic_distance_cm": None,
            "estimated_depth_cm": None,
            "sensor_fusion_score": None,
            "sensor_source": "demo-ultrasonic",
            "sensor_samples_cm": [],
        }

    x1, y1, x2, y2 = [float(v) for v in bbox[:4]]
    width = max(abs(x2 - x1), 1.0)
    height = max(abs(y2 - y1), 1.0)
    area_ratio = min((width * height) / float(frame_w * frame_h), 0.35)
    center_x = (x1 + x2) / 2.0
    center_bias = 1.0 - min(abs((center_x / frame_w) - 0.5) * 2.0, 1.0) * 0.18

    seed = int(x1 * 17 + y1 * 31 + x2 * 43 + y2 * 59)
    rng = random.Random(seed)

    min_depth = _SEVERITY_MIN_DEPTH_CM.get(severity, 2.5)
    depth_cm = min_depth + area_ratio * 26.0 + confidence * 2.4
    depth_cm *= center_bias
    depth_cm = round(min(max(depth_cm, min_depth), 18.5), 1)

    baseline_clearance_cm = 24.0
    distance_cm = round(max(4.5, baseline_clearance_cm - depth_cm + rng.uniform(-0.35, 0.35)), 1)

    samples = [
        round(max(4.0, distance_cm + rng.uniform(-0.55, 0.55)), 2)
        for _ in range(6)
    ]
    fusion_score = round(min(0.99, 0.62 + confidence * 0.2 + min(depth_cm / 20.0, 1.0) * 0.18), 2)

    return {
        "ultrasonic_distance_cm": distance_cm,
        "estimated_depth_cm": depth_cm,
        "sensor_fusion_score": fusion_score,
        "sensor_source": "demo-ultrasonic",
        "sensor_samples_cm": samples,
    }