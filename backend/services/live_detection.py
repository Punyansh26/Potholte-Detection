"""Lazy-loaded detector runtime for browser and stream inference."""

from __future__ import annotations

import base64
from functools import lru_cache

import cv2
import numpy as np

from detector.inference import PotholeDetector


@lru_cache(maxsize=1)
def get_detector() -> PotholeDetector:
    """Create and cache the YOLO detector on first use."""
    return PotholeDetector()


def decode_frame(image_b64: str) -> np.ndarray:
    """Decode a base64-encoded image into an OpenCV BGR frame."""
    raw = base64.b64decode(image_b64)
    arr = np.frombuffer(raw, dtype=np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError("Invalid image payload")
    return frame