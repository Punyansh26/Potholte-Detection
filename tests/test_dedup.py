"""Tests for spatial deduplication logic."""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient
from backend.main import app
from backend.database import init_db, engine, Base

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


def test_two_detections_within_2_5m_merge():
    """Two reports within 2.5m should merge into one Pothole_ID."""
    # First report
    r1 = client.post("/detections", json={
        "lat": 19.076000, "lon": 72.877700,
        "bbox": [100, 200, 300, 400], "confidence": 0.90,
    })
    pid1 = r1.json()["pothole_id"]
    assert r1.json()["is_new"] is True

    # Second report — ~1m away (approx 0.000009 degrees)
    r2 = client.post("/detections", json={
        "lat": 19.076009, "lon": 72.877709,
        "bbox": [110, 210, 310, 410], "confidence": 0.85,
    })
    pid2 = r2.json()["pothole_id"]
    assert r2.json()["is_new"] is False
    assert pid1 == pid2, "Should merge into same pothole"


def test_two_detections_far_apart_separate():
    """Two reports > 2.5m apart should create separate Pothole_IDs."""
    r1 = client.post("/detections", json={
        "lat": 19.076000, "lon": 72.877700,
        "bbox": [100, 200, 300, 400], "confidence": 0.90,
    })
    pid1 = r1.json()["pothole_id"]

    # ~50m away (0.00045 degrees ≈ 50m)
    r2 = client.post("/detections", json={
        "lat": 19.076450, "lon": 72.877700,
        "bbox": [100, 200, 300, 400], "confidence": 0.88,
    })
    pid2 = r2.json()["pothole_id"]
    assert pid1 != pid2, "Should be separate potholes"


def test_dedup_updates_detection_count():
    """Merged detections should increment count and update confidence."""
    client.post("/detections", json={
        "lat": 19.076000, "lon": 72.877700,
        "bbox": [100, 200, 300, 400], "confidence": 0.90,
    })
    client.post("/detections", json={
        "lat": 19.076005, "lon": 72.877705,
        "bbox": [120, 220, 320, 420], "confidence": 0.80,
    })
    client.post("/detections", json={
        "lat": 19.076003, "lon": 72.877703,
        "bbox": [130, 230, 330, 430], "confidence": 0.95,
    })

    potholes = client.get("/potholes").json()
    assert len(potholes) == 1
    assert potholes[0]["detection_count"] == 3


def test_haversine_distance():
    """Verify Haversine distance computation."""
    from backend.services.dedup import haversine_meters

    # Same point
    assert haversine_meters(19.076, 72.877, 19.076, 72.877) == 0.0

    # Known distance: ~111m per degree latitude
    d = haversine_meters(19.076, 72.877, 19.077, 72.877)
    assert 110 < d < 112, f"Expected ~111m, got {d}"
