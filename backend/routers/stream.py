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
from typing import Generator

import cv2
import numpy as np
import httpx

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from config import settings

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

    if model:
        try:
            results = model(frame, conf=conf_threshold, verbose=False)
            for r in results:
                for box in r.boxes:
                    x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
                    conf = float(box.conf[0])
                    severity = _estimate_severity([x1, y1, x2, y2], w, h)
                    color_rgb = _SEV_COLORS.get(severity, (128, 128, 128))
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
                    })
        except Exception as e:
            logger.error("Inference error: %s", e)

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
