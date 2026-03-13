"""Privacy pipeline — face & license plate blur before upload.

Uses OpenCV Haar cascades for face detection and a simple contour-based
approach for license plates. Falls back gracefully if cascades are missing.

Usage:
  from privacy.blur import blur_pii
  clean_img = blur_pii(cv2_bgr_image)
"""

from __future__ import annotations

import cv2
import numpy as np
import logging

logger = logging.getLogger(__name__)

# Haar cascade paths (bundled with OpenCV)
_FACE_CASCADE_PATH = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
_PLATE_CASCADE_PATH = cv2.data.haarcascades + "haarcascade_russian_plate_number.xml"

_face_cascade = None
_plate_cascade = None


def _get_face_cascade():
    global _face_cascade
    if _face_cascade is None:
        _face_cascade = cv2.CascadeClassifier(_FACE_CASCADE_PATH)
        if _face_cascade.empty():
            logger.warning("Face cascade not found — face blur disabled")
            _face_cascade = False
    return _face_cascade if _face_cascade else None


def _get_plate_cascade():
    global _plate_cascade
    if _plate_cascade is None:
        _plate_cascade = cv2.CascadeClassifier(_PLATE_CASCADE_PATH)
        if _plate_cascade.empty():
            logger.warning("Plate cascade not found — plate blur disabled")
            _plate_cascade = False
    return _plate_cascade if _plate_cascade else None


def _apply_blur(img: np.ndarray, rects: list, ksize: int = 51) -> np.ndarray:
    """Apply heavy Gaussian blur to regions defined by (x,y,w,h) rects."""
    for (x, y, w, h) in rects:
        roi = img[y:y+h, x:x+w]
        img[y:y+h, x:x+w] = cv2.GaussianBlur(roi, (ksize, ksize), 30)
    return img


def detect_faces(img: np.ndarray) -> list:
    cascade = _get_face_cascade()
    if cascade is None:
        return []
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))


def detect_plates(img: np.ndarray) -> list:
    cascade = _get_plate_cascade()
    if cascade is None:
        return []
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4, minSize=(60, 20))


def blur_pii(img: np.ndarray) -> np.ndarray:
    """Detect faces and license plates and blur them irreversibly.

    Returns a new image with PII regions blurred.
    """
    result = img.copy()

    faces = detect_faces(result)
    if len(faces) > 0:
        logger.info("Blurring %d face(s)", len(faces))
        result = _apply_blur(result, faces)

    plates = detect_plates(result)
    if len(plates) > 0:
        logger.info("Blurring %d plate(s)", len(plates))
        result = _apply_blur(result, plates)

    return result


# ── CLI test ──────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python privacy/blur.py <image_path> [output_path]")
        sys.exit(1)

    img = cv2.imread(sys.argv[1])
    if img is None:
        print(f"Cannot read: {sys.argv[1]}")
        sys.exit(1)

    result = blur_pii(img)
    out_path = sys.argv[2] if len(sys.argv) > 2 else "blurred_output.jpg"
    cv2.imwrite(out_path, result)
    print(f"Blurred image saved to {out_path}")
    print(f"  Faces detected: {len(detect_faces(img))}")
    print(f"  Plates detected: {len(detect_plates(img))}")
