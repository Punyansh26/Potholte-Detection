"""Live camera streaming router.

Pulls frames from a phone/webcam stream (e.g. IP Webcam Android app),
runs YOLOv8 pothole detection on each frame, draws bounding boxes,
and streams back as MJPEG so the frontend can display it in a plain
<img> tag with real-time annotations.

Also POSTs detections to the database asynchronously.

Usage:
  Start backend, then in the dashboard click "Live Cam" and enter:
    http://192.168.0.103:8080/video   (IP Webcam Android MJPEG)
    0                                  (local webcam)
"""

from __future__ import annotations

import io
import os
import sys
import time
import base64
import asyncio
import logging
import threading
import random
from typing import Generator

import cv2
import numpy as np
import httpx

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from backend.models import LiveSensorTelemetry, LiveTelemetryResponse
from backend.services.phone_telemetry import get_latest
from backend.services.sensor_classifier import build_telemetry_view
from config import settings
from detector.demo_ultrasonic import synthesize_ultrasonic_profile

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/stream", tags=["stream"])

# ── Severity estimation (local copy — avoids circular import) ─────────────

_SEV_COLORS = {
    "low":      (34, 197, 94),
    "medium":   (234, 179, 8),
    "high":     (249, 115, 22),
    "critical": (239, 68, 68),
}


def _estimate_severity(bbox, w, h):
    x1, y1, x2, y2 = bbox
    ratio = abs(x2 - x1) * abs(y2 - y1) / (w * h) if w * h else 0
    if ratio > 0.15: return "critical"
    if ratio > 0.08: return "high"
    if ratio > 0.03: return "medium"
    return "low"


# ── YOLO loader (lazy — loads once on first request) ──────────────────────

_model = None
_model_lock = threading.Lock()
_telemetry_lock = threading.Lock()
_latest_telemetry = None


def _severity_weight(severity: str) -> int:
    return {
        "none": 0,
        "low": 1,
        "medium": 2,
        "high": 3,
        "critical": 4,
    }.get(severity, 0)


def _advisory_for(severity: str, detection_count: int) -> str:
    if severity == "critical":
        return "Dispatch repair crew and slow platform immediately"
    if severity == "high":
        return "Flag lane for inspection and reduce approach speed"
    if detection_count > 0:
        return "Maintain scan and log rough segment"
    return "Monitoring road surface"


def _build_mock_telemetry(
    detection_count: int = 0,
    max_severity: str = "none",
    confidence: float = 0.0,
    ultrasonic_distance_cm: float | None = None,
    estimated_depth_cm: float | None = None,
    sensor_fusion_score: float | None = None,
) -> dict[str, float | int | str | None]:
    severity_boost = _severity_weight(max_severity)
    tick = int(time.time() * 2)
    rng = random.Random(f"vehicle:{tick}:{detection_count}:{max_severity}:{confidence:.2f}")

    vibration_rms_g = round(0.22 + severity_boost * 0.13 + detection_count * 0.04 + rng.uniform(0.01, 0.11), 2)
    peak_accel_g = round(vibration_rms_g + 0.28 + rng.uniform(0.06, 0.34), 2)
    speed_kph = round(max(8.0, 31 + rng.uniform(-4.5, 5.5) - severity_boost * 2.7), 1)
    pitch_deg = round(rng.uniform(-1.4, 1.4), 1)
    roll_deg = round(rng.uniform(-2.2, 2.2), 1)
    yaw_deg = round((tick * 7 + rng.uniform(-4.0, 4.0)) % 360, 1)
    sensor_source = "demo-vehicle-imu"

    roughness_index = round(min(100.0, 16 + vibration_rms_g * 42 + severity_boost * 9 + detection_count * 2.5), 1)
    shock_index = int(min(100, round(peak_accel_g * 18 + severity_boost * 9 + detection_count * 3)))

    return {
        "mode": "vehicle",
        "sensor_source": sensor_source,
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "detection_count": detection_count,
        "max_severity": max_severity,
        "vibration_rms_g": vibration_rms_g,
        "peak_accel_g": peak_accel_g,
        "shock_index": shock_index,
        "roughness_index": roughness_index,
        "speed_kph": speed_kph,
        "pitch_deg": pitch_deg,
        "roll_deg": roll_deg,
        "yaw_deg": yaw_deg,
        "ultrasonic_distance_cm": ultrasonic_distance_cm,
        "estimated_depth_cm": estimated_depth_cm,
        "sensor_fusion_score": sensor_fusion_score,
        "advisory": _advisory_for(max_severity, detection_count),
    }


def _store_latest_telemetry(telemetry: dict[str, float | int | str | None]) -> None:
    global _latest_telemetry
    with _telemetry_lock:
        _latest_telemetry = telemetry.copy()


def _current_telemetry() -> LiveSensorTelemetry:
    latest_phone = get_latest()
    if latest_phone:
        model_score = latest_phone.get("model_score") if isinstance(latest_phone, dict) else None
        view = build_telemetry_view(latest_phone, model_score)
        return LiveSensorTelemetry(**view)

    with _telemetry_lock:
        telemetry = _latest_telemetry.copy() if _latest_telemetry else None

    if not telemetry:
        telemetry = _build_mock_telemetry()
    elif telemetry.get("mode") != "vehicle":
        telemetry = _build_mock_telemetry(
            detection_count=int(telemetry.get("detection_count") or 0),
            max_severity=str(telemetry.get("max_severity") or "none"),
            ultrasonic_distance_cm=telemetry.get("ultrasonic_distance_cm"),
            estimated_depth_cm=telemetry.get("estimated_depth_cm"),
            sensor_fusion_score=telemetry.get("sensor_fusion_score"),
        )

    return LiveSensorTelemetry(**telemetry)


def _register_torch_safe_globals() -> None:
    """Allow trusted Ultralytics classes for PyTorch >= 2.6 checkpoints."""
    try:
        import torch
        from ultralytics.nn.tasks import (
            ClassificationModel,
            DetectionModel,
            OBBModel,
            PoseModel,
            SegmentationModel,
        )

        torch.serialization.add_safe_globals([
            ClassificationModel,
            DetectionModel,
            SegmentationModel,
            PoseModel,
            OBBModel,
        ])
    except Exception:
        pass


def _get_model():
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                try:
                    try:
                        from ultralyticsplus import YOLO
                    except ImportError:
                        from ultralytics import YOLO

                    os.environ.setdefault("TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD", "1")
                    _register_torch_safe_globals()
                    model_path = os.environ.get("YOLO_MODEL", settings.yolo_model)
                    _model = YOLO(model_path)
                    _model.overrides["conf"] = settings.yolo_conf
                    _model.overrides["iou"] = settings.yolo_iou
                    _model.overrides["agnostic_nms"] = settings.yolo_agnostic_nms
                    _model.overrides["max_det"] = settings.yolo_max_det
                    logger.info("YOLO model loaded: %s", model_path)
                except Exception as e:
                    logger.error("Failed to load YOLO model: %s", e)
                    _model = False   # mark as failed so we don't retry every frame
    return _model if _model else None


# ── Frame generator ──────────────────────────────────────────────────────

def _annotate_frame(frame: np.ndarray, conf_threshold: float, post_url: str | None):
    """Run YOLO on frame, draw boxes, optionally POST detections."""
    model = _get_model()
    h, w = frame.shape[:2]
    detections_to_post = []
    top_profile = None
    top_confidence = 0.0
    top_severity = "none"

    if model:
        try:
            results = model(frame, conf=conf_threshold, verbose=False)
            for r in results:
                for box in r.boxes:
                    x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
                    conf = float(box.conf[0])
                    severity = _estimate_severity([x1, y1, x2, y2], w, h)
                    color_rgb = _SEV_COLORS.get(severity, (128, 128, 128))
                    ultrasonic_profile = synthesize_ultrasonic_profile([x1, y1, x2, y2], w, h, conf, severity)
                    # OpenCV uses BGR
                    color_bgr = (color_rgb[2], color_rgb[1], color_rgb[0])

                    # Draw bounding box
                    thickness = 3 if severity in ("critical", "high") else 2
                    cv2.rectangle(frame, (x1, y1), (x2, y2), color_bgr, thickness)

                    # Label background
                    label = f"Pothole {severity} {conf:.0%}"
                    (lw, lh), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
                    cv2.rectangle(frame, (x1, y1 - lh - 8), (x1 + lw + 4, y1), color_bgr, -1)
                    cv2.putText(frame, label, (x1 + 2, y1 - 4),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)

                    # Pulse ring for critical
                    if severity == "critical":
                        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
                        radius = max(abs(x2 - x1), abs(y2 - y1)) // 2
                        cv2.circle(frame, (cx, cy), radius + 10, color_bgr, 1)

                    detections_to_post.append({
                        "camera_id": settings.camera_id,
                        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                        "lat": settings.default_lat,
                        "lon": settings.default_lon,
                        "bbox": [x1, y1, x2, y2],
                        "confidence": round(conf, 4),
                        "severity_est": severity,
                        **ultrasonic_profile,
                    })

                    if _severity_weight(severity) >= _severity_weight(top_severity):
                        top_profile = ultrasonic_profile
                        top_confidence = conf
                        top_severity = severity
        except Exception as e:
            logger.error("Inference error: %s", e)

    telemetry = _build_mock_telemetry(
        detection_count=len(detections_to_post),
        max_severity=top_severity,
        confidence=top_confidence,
        ultrasonic_distance_cm=(top_profile or {}).get("ultrasonic_distance_cm"),
        estimated_depth_cm=(top_profile or {}).get("estimated_depth_cm"),
        sensor_fusion_score=(top_profile or {}).get("sensor_fusion_score"),
    )
    _store_latest_telemetry(telemetry)

    for detection in detections_to_post:
        detection["sensor_source"] = str(telemetry.get("sensor_source") or detection.get("sensor_source") or "")
        detection["vibration_rms_g"] = telemetry.get("vibration_rms_g")
        detection["peak_accel_g"] = telemetry.get("peak_accel_g")
        detection["shock_index"] = telemetry.get("shock_index")
        detection["roughness_index"] = telemetry.get("roughness_index")
        detection["speed_kph"] = telemetry.get("speed_kph")
        detection["pitch_deg"] = telemetry.get("pitch_deg")
        detection["roll_deg"] = telemetry.get("roll_deg")
        detection["yaw_deg"] = telemetry.get("yaw_deg")

    # Overlay: status bar at top
    bar_h = 36
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, bar_h), (10, 14, 26), -1)
    cv2.addWeighted(overlay, 0.75, frame, 0.25, 0, frame)
    status = f"PotholeGuard Live  |  {len(detections_to_post)} detection(s)" \
             if detections_to_post else "PotholeGuard Live  |  Scanning…"
    cv2.putText(frame, status, (10, 24),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (180, 190, 255), 2)

    # POST detections to backend (fire-and-forget)
    if post_url and detections_to_post:
        def _post(dets, url):
            for d in dets:
                try:
                    httpx.post(url, json=d, timeout=3)
                except Exception:
                    pass
        threading.Thread(target=_post, args=(detections_to_post, post_url), daemon=True).start()

    return frame


def _frame_generator(
    source: str,
    conf: float,
    post_url: str | None,
    skip: int,
    max_dim: int,
    mode: str,
) -> Generator[bytes, None, None]:
    """Yield MJPEG frames."""
    # Resolve source
    src = int(source) if source.isdigit() else source

    cap = cv2.VideoCapture(src)
    if not cap.isOpened():
        # Yield a single error frame
        err = np.zeros((240, 640, 3), dtype=np.uint8)
        cv2.putText(err, f"Cannot open: {source}", (20, 120),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 220), 2)
        _, buf = cv2.imencode(".jpg", err)
        yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buf.tobytes() + b"\r\n")
        return

    frame_idx = 0
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                # Reconnect once for network streams
                cap.release()
                time.sleep(0.5)
                cap = cv2.VideoCapture(src)
                continue

            frame_idx += 1
            if frame_idx % skip != 0:
                # Still yield raw frame for smooth video
                h, w = frame.shape[:2]
                if max(h, w) > max_dim:
                    scale = max_dim / max(h, w)
                    frame = cv2.resize(frame, (int(w * scale), int(h * scale)))
                _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
                yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buf.tobytes() + b"\r\n")
                continue

            # Resize for inference
            h, w = frame.shape[:2]
            if max(h, w) > max_dim:
                scale = max_dim / max(h, w)
                frame = cv2.resize(frame, (int(w * scale), int(h * scale)))

            frame = _annotate_frame(frame, conf, post_url)

            _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buf.tobytes() + b"\r\n")
    finally:
        cap.release()


# ── Endpoint ─────────────────────────────────────────────────────────────

@router.get("/video")
def live_stream(
    source: str = Query(default="0", description="Camera source: 0-9 for webcam, or full URL"),
    conf: float = Query(default=0.25, description="Detection confidence threshold"),
    post: bool = Query(default=True, description="Auto-POST detections to DB"),
    skip: int = Query(default=2, description="Run YOLO every N frames (1=every frame)"),
    max_dim: int = Query(default=640, description="Max frame dimension for inference"),
):
    """MJPEG stream with real-time YOLO pothole detection overlaid.

    Embed in the frontend with:
      <img src="/stream/video?source=http://192.168.0.103:8080/video">
    """
    post_url = f"http://localhost:{os.environ.get('PORT', 8000)}/detections" if post else None
    return StreamingResponse(
        _frame_generator(source, conf, post_url, skip, max_dim),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/telemetry", response_model=LiveTelemetryResponse)
def live_telemetry():
    """Return the latest mock sensor telemetry for the live camera feed."""
    return LiveTelemetryResponse(telemetry=_current_telemetry())
