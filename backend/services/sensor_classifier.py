"""Lightweight sensor-only pothole classifier for hackathon use."""

from __future__ import annotations

import math
from typing import Any


class SensorClassificationResult(dict):
    """Small dict wrapper for model results."""


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def compute_features(payload: dict) -> dict[str, float | None]:
    ax = _safe_float(payload.get("accel_x"))
    ay = _safe_float(payload.get("accel_y"))
    az = _safe_float(payload.get("accel_z"))
    speed_kph = _safe_float(payload.get("speed_kph"))
    vision_conf = _safe_float(payload.get("vision_confidence"))

    accel_mag = None
    shock_g = None
    if ax is not None or ay is not None or az is not None:
        ax = ax or 0.0
        ay = ay or 0.0
        az = az or 0.0
        accel_mag = math.sqrt(ax * ax + ay * ay + az * az)
        # DeviceMotion often includes gravity in m/s^2.
        shock_g = max(0.0, (accel_mag - 9.81) / 9.81)

    return {
        "accel_mag": accel_mag,
        "shock_g": shock_g,
        "speed_kph": speed_kph,
        "vision_confidence": vision_conf,
    }


def classify_pothole(payload: dict) -> SensorClassificationResult:
    features = compute_features(payload)
    shock_g = features.get("shock_g") or 0.0
    speed_kph = features.get("speed_kph") or 0.0
    vision_conf = features.get("vision_confidence") or 0.0

    # Hackathon heuristic scoring (0-1)
    score = 0.0
    score += min(shock_g / 0.8, 1.0) * 0.5
    score += min(speed_kph / 50.0, 1.0) * 0.2
    score += min(vision_conf, 1.0) * 0.3

    is_pothole = score >= 0.55

    return SensorClassificationResult(
        is_pothole=is_pothole,
        score=round(score, 3),
        features=features,
    )


def build_telemetry_view(payload: dict, model_score: float | None = None) -> dict[str, float | int | str | None]:
    features = compute_features(payload)
    shock_g = features.get("shock_g")
    accel_mag = features.get("accel_mag")

    vibration_rms_g = round(accel_mag / 9.81, 2) if accel_mag is not None else 0.0
    peak_accel_g = round(vibration_rms_g + (shock_g or 0.0), 2) if shock_g is not None else vibration_rms_g
    shock_index = int(min(100, max(0.0, (shock_g or 0.0) * 120)))
    roughness_index = round(min(100.0, vibration_rms_g * 45 + (shock_g or 0.0) * 30), 1)

    return {
        "mode": "vehicle",
        "sensor_source": payload.get("device_id") or "phone-sensor",
        "captured_at": payload.get("timestamp") or "",
        "detection_count": 0,
        "max_severity": "high" if (model_score or 0) >= 0.8 else "medium" if (model_score or 0) >= 0.6 else "low",
        "vibration_rms_g": vibration_rms_g,
        "peak_accel_g": peak_accel_g,
        "shock_index": shock_index,
        "roughness_index": roughness_index,
        "speed_kph": payload.get("speed_kph"),
        "pitch_deg": payload.get("gyro_pitch") or 0.0,
        "roll_deg": payload.get("gyro_roll") or 0.0,
        "yaw_deg": payload.get("gyro_yaw") or 0.0,
        "ultrasonic_distance_cm": None,
        "estimated_depth_cm": None,
        "sensor_fusion_score": model_score,
        "advisory": "Phone telemetry live",
    }
