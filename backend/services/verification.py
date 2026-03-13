"""Verification service — image comparison for repair detection.

Compares a new snapshot against previous snapshots of the same pothole
using ORB feature matching and structural similarity (SSIM).

Decision logic:
  - If SSIM < 0.35 (images very different) → likely repaired
  - If SSIM ≥ 0.35 and status was "Closed" on portal → escalate / appeal
"""

from __future__ import annotations

import base64
import io
import logging
from typing import Tuple

import cv2
import numpy as np
from skimage.metrics import structural_similarity as ssim

logger = logging.getLogger(__name__)


def decode_base64_image(b64: str) -> np.ndarray:
    """Decode a base64 JPEG/PNG string to an OpenCV BGR image."""
    img_bytes = base64.b64decode(b64)
    arr = np.frombuffer(img_bytes, dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


def compare_images(img1: np.ndarray, img2: np.ndarray) -> Tuple[float, int]:
    """Return (SSIM score, ORB match count) between two images.

    Both images are resized to 256×256 grey for a fast comparison.
    """
    size = (256, 256)
    g1 = cv2.resize(cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY), size)
    g2 = cv2.resize(cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY), size)

    # Structural similarity
    score = ssim(g1, g2)

    # ORB feature matching
    orb = cv2.ORB_create(nfeatures=500)
    kp1, des1 = orb.detectAndCompute(g1, None)
    kp2, des2 = orb.detectAndCompute(g2, None)

    good_matches = 0
    if des1 is not None and des2 is not None and len(des1) > 0 and len(des2) > 0:
        bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
        matches = bf.match(des1, des2)
        good_matches = sum(1 for m in matches if m.distance < 50)

    return float(score), good_matches


def is_repaired(
    new_b64: str,
    old_b64: str | None,
    ssim_threshold: float = 0.35,
) -> Tuple[bool, float, str]:
    """Determine if a pothole has been repaired.

    Returns (repaired, similarity_score, action).
    """
    if not old_b64:
        return False, 0.0, "no_previous_image"

    try:
        new_img = decode_base64_image(new_b64)
        old_img = decode_base64_image(old_b64)
        similarity, match_count = compare_images(old_img, new_img)
    except Exception as exc:
        logger.warning("Image comparison failed: %s", exc)
        return False, 0.0, "comparison_failed"

    if similarity < ssim_threshold:
        return True, similarity, "marked_repaired"
    return False, similarity, "still_damaged"
