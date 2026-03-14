"""YOLOv8 Pothole Inference Pipeline.

Load a YOLOv8 model (PyTorch or ONNX) and run inference on images,
video files, or a webcam stream.  Outputs JSON detection records.
"""

from __future__ import annotations

import json
import time
import base64
import os
import cv2
import numpy as np
from pathlib import Path
from typing import List, Dict, Any

from detector.demo_ultrasonic import synthesize_ultrasonic_profile

try:
    from ultralyticsplus import YOLO
    _YOLO_IMPORT_HINT = "ultralyticsplus"
except ImportError:
    try:
        from ultralytics import YOLO
        _YOLO_IMPORT_HINT = "ultralytics"
    except ImportError:
        YOLO = None   # allow import without ultralytics for lightweight envs
        _YOLO_IMPORT_HINT = "none"


DEFAULT_MODEL_ID = "keremberke/yolov8n-pothole-segmentation"


def _register_torch_safe_globals() -> None:
    """Allow trusted Ultralytics model classes for PyTorch >= 2.6 safe loading."""
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
        # Safe-global registration is best-effort for compatibility.
        pass


# Severity estimation from bounding-box area relative to frame
def _estimate_severity(bbox: list, frame_w: int, frame_h: int) -> str:
    x1, y1, x2, y2 = bbox
    area = abs(x2 - x1) * abs(y2 - y1)
    ratio = area / (frame_w * frame_h) if frame_w * frame_h else 0
    if ratio > 0.15:
        return "critical"
    if ratio > 0.08:
        return "high"
    if ratio > 0.03:
        return "medium"
    return "low"


class PotholeDetector:
    """Thin wrapper around a YOLOv8 model for pothole detection."""

    def __init__(self, model_path: str | None = None, conf_threshold: float = 0.25):
        if YOLO is None:
            raise RuntimeError(
                "YOLO backend is not installed. Install ultralyticsplus (preferred) or ultralytics."
            )
        resolved_model = model_path or os.environ.get("YOLO_MODEL", DEFAULT_MODEL_ID)
        iou_threshold = float(os.environ.get("YOLO_IOU", "0.45"))
        agnostic_nms = os.environ.get("YOLO_AGNOSTIC_NMS", "false").strip().lower() == "true"
        max_det = int(os.environ.get("YOLO_MAX_DET", "1000"))

        # PyTorch >= 2.6 defaults to weights_only=True; this trusted model requires full ckpt load.
        os.environ.setdefault("TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD", "1")
        _register_torch_safe_globals()
        self.model = YOLO(resolved_model)
        self.conf_threshold = conf_threshold
        self.model.overrides["conf"] = conf_threshold
        self.model.overrides["iou"] = iou_threshold
        self.model.overrides["agnostic_nms"] = agnostic_nms
        self.model.overrides["max_det"] = max_det
        self.model_path = resolved_model
        self.iou_threshold = iou_threshold
        self.agnostic_nms = agnostic_nms
        self.max_det = max_det

    def detect_image(self, img: np.ndarray, camera_id: str = "edge-001",
                     lat: float = 0.0, lon: float = 0.0) -> List[Dict[str, Any]]:
        """Run inference on a single BGR image and return detection dicts."""
        h, w = img.shape[:2]
        results = self.model(
            img,
            conf=self.conf_threshold,
            iou=self.iou_threshold,
            agnostic_nms=self.agnostic_nms,
            max_det=self.max_det,
            verbose=False,
        )
        detections = []

        for r in results:
            for box in r.boxes:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                conf = float(box.conf[0])
                cls_id = int(box.cls[0])
                cls_name = r.names.get(cls_id, str(cls_id))

                bbox = [int(x1), int(y1), int(x2), int(y2)]
                severity = _estimate_severity(bbox, w, h)
                ultrasonic_profile = synthesize_ultrasonic_profile(bbox, w, h, conf, severity)

                # Crop snapshot and encode
                crop = img[int(y1):int(y2), int(x1):int(x2)]
                _, buf = cv2.imencode('.jpg', crop, [cv2.IMWRITE_JPEG_QUALITY, 85])
                snap_b64 = base64.b64encode(buf).decode()

                detections.append({
                    "camera_id": camera_id,
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                    "lat": lat,
                    "lon": lon,
                    "bbox": bbox,
                    "confidence": round(conf, 4),
                    "severity_est": severity,
                    "class_name": cls_name,
                    "snapshot_base64": snap_b64,
                    **ultrasonic_profile,
                })
        return detections

    def detect_video(self, source, camera_id: str = "edge-001",
                     lat: float = 0.0, lon: float = 0.0,
                     skip_frames: int = 5,
                     max_frames: int = 0) -> List[Dict[str, Any]]:
        """Process a video file or webcam (source=0) frame by frame."""
        cap = cv2.VideoCapture(source)
        all_detections: List[Dict[str, Any]] = []
        frame_idx = 0

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            frame_idx += 1
            if frame_idx % skip_frames != 0:
                continue
            dets = self.detect_image(frame, camera_id, lat, lon)
            all_detections.extend(dets)

            if max_frames and frame_idx >= max_frames:
                break

        cap.release()
        return all_detections


# ── CLI usage ─────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run YOLOv8 pothole inference")
    parser.add_argument("--source", default="0", help="Webcam id, video path, or image path")
    parser.add_argument("--model", default=os.environ.get("YOLO_MODEL", DEFAULT_MODEL_ID), help="Model id/path (.pt/.onnx/HF repo id)")
    parser.add_argument("--conf", type=float, default=0.25, help="Confidence threshold")
    parser.add_argument("--lat", type=float, default=19.0760)
    parser.add_argument("--lon", type=float, default=72.8777)
    parser.add_argument("--camera-id", default="edge-001")
    parser.add_argument("--skip", type=int, default=5, help="Process every Nth frame")
    parser.add_argument("--output", default=None, help="Save detections JSON to file")
    args = parser.parse_args()

    detector = PotholeDetector(args.model, args.conf)
    print(f"Using YOLO backend={_YOLO_IMPORT_HINT} model={detector.model_path}")

    src = args.source
    if src.isdigit():
        src = int(src)

    if isinstance(src, int) or src.endswith(('.mp4', '.avi', '.mkv', '.mov')):
        dets = detector.detect_video(src, args.camera_id, args.lat, args.lon, args.skip)
    else:
        img = cv2.imread(src)
        if img is None:
            raise FileNotFoundError(f"Cannot read image: {src}")
        dets = detector.detect_image(img, args.camera_id, args.lat, args.lon)

    print(f"Found {len(dets)} detections")
    for d in dets:
        d.pop("snapshot_base64", None)  # don't flood terminal
        print(json.dumps(d, indent=2))

    if args.output:
        # Keep base64 in file output
        with open(args.output, "w") as f:
            json.dump(dets, f, indent=2)
        print(f"Saved to {args.output}")
