"""Tests for the verification / repair detection pipeline."""

import sys
import os
import base64
import pytest
import numpy as np
import cv2

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.services.verification import is_repaired, compare_images


def _make_test_image(color=(100, 100, 100), size=(256, 256)):
    """Create a simple solid-color image and return base64."""
    img = np.full((*size, 3), color, dtype=np.uint8)
    _, buf = cv2.imencode('.jpg', img)
    return base64.b64encode(buf).decode()


def test_identical_images_not_repaired():
    """Two identical images should NOT be marked as repaired."""
    b64 = _make_test_image((50, 50, 50))
    repaired, sim, action = is_repaired(b64, b64)
    assert not repaired
    assert sim > 0.5
    assert action == "still_damaged"


def test_very_different_images_repaired():
    """Very different images (e.g. pothole vs clean road) should be marked repaired."""
    dark = _make_test_image((20, 20, 20))
    light = _make_test_image((220, 220, 220))
    repaired, sim, action = is_repaired(light, dark)
    assert repaired
    assert sim < 0.35
    assert action == "marked_repaired"


def test_no_previous_image():
    """If no old image exists, can't determine repair status."""
    b64 = _make_test_image()
    repaired, sim, action = is_repaired(b64, None)
    assert not repaired
    assert action == "no_previous_image"


def test_compare_images_returns_tuple():
    img1 = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
    img2 = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
    ssim_score, match_count = compare_images(img1, img2)
    assert isinstance(ssim_score, float)
    assert isinstance(match_count, int)
