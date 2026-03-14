"""Tests for backend API endpoints."""

import sys
import os
import base64
import pytest
import cv2
import numpy as np

# Ensure project root is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient
from backend.main import app
from backend.database import init_db, engine, Base

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_db():
    """Reset database before each test."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


# ── Health ────────────────────────────────────────────────────────

def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# ── POST /detections ─────────────────────────────────────────────

def test_post_detection_creates_pothole():
    payload = {
        "camera_id": "test-cam",
        "lat": 19.0760,
        "lon": 72.8777,
        "bbox": [100, 200, 300, 400],
        "confidence": 0.92,
    }
    resp = client.post("/detections", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_new"] is True
    assert data["pothole_id"] >= 1
    assert data["severity"] in ("low", "medium", "high", "critical")


def test_post_detection_with_snapshot():
    # Tiny 1x1 JPEG as base64
    tiny_jpg = base64.b64encode(b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00').decode()
    payload = {
        "camera_id": "test-cam",
        "lat": 19.0760,
        "lon": 72.8777,
        "bbox": [10, 20, 300, 400],
        "confidence": 0.88,
        "snapshot_base64": tiny_jpg,
    }
    resp = client.post("/detections", json=payload)
    assert resp.status_code == 200


def test_live_detect_persists_detection(monkeypatch):
    img = np.full((24, 24, 3), 180, dtype=np.uint8)
    ok, buf = cv2.imencode(".jpg", img)
    assert ok is True

    class StubDetector:
        def detect_image(self, frame, camera_id, lat, lon):
            assert frame.shape[0] > 0
            assert camera_id == "browser-camera"
            return [{
                "camera_id": camera_id,
                "timestamp": "2026-03-14T12:00:00+0000",
                "lat": lat,
                "lon": lon,
                "bbox": [1, 2, 12, 16],
                "confidence": 0.93,
                "severity_est": "medium",
                "class_name": "pothole",
                "snapshot_base64": base64.b64encode(buf).decode(),
            }]

    import backend.routers.detections as detections_router

    monkeypatch.setattr(detections_router, "get_detector", lambda: StubDetector())

    resp = client.post("/live/detect", json={
        "image_base64": base64.b64encode(buf).decode(),
        "camera_id": "browser-camera",
        "lat": 19.076,
        "lon": 72.8777,
        "persist": True,
    })

    assert resp.status_code == 200
    data = resp.json()
    assert data["frame_width"] == 24
    assert data["frame_height"] == 24
    assert len(data["detections"]) == 1
    assert data["detections"][0]["pothole_id"] == 1
    assert data["detections"][0]["is_new"] is True


# ── GET /potholes ────────────────────────────────────────────────

def test_list_potholes_empty():
    resp = client.get("/potholes")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_potholes_after_detection():
    client.post("/detections", json={
        "lat": 19.0760, "lon": 72.8777,
        "bbox": [100, 200, 300, 400], "confidence": 0.9,
    })
    resp = client.get("/potholes")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["lat"] == 19.076


def test_filter_by_severity():
    # Create a detection that would be 'medium' severity based on bbox
    client.post("/detections", json={
        "lat": 19.0760, "lon": 72.8777,
        "bbox": [100, 200, 200, 250], "confidence": 0.9,
        "severity_est": "medium",
    })
    # Filter for critical (should be empty)
    resp = client.get("/potholes?severity=critical")
    assert resp.status_code == 200
    assert len(resp.json()) == 0

    # Filter for medium
    resp = client.get("/potholes?severity=medium")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


# ── GET /potholes/{id} ───────────────────────────────────────────

def test_get_pothole_detail():
    r = client.post("/detections", json={
        "lat": 19.0760, "lon": 72.8777,
        "bbox": [100, 200, 300, 400], "confidence": 0.9,
    })
    pid = r.json()["pothole_id"]
    resp = client.get(f"/potholes/{pid}")
    assert resp.status_code == 200
    assert resp.json()["pothole_id"] == pid


def test_get_pothole_not_found():
    resp = client.get("/potholes/99999")
    assert resp.status_code == 404


# ── POST /manual_report ──────────────────────────────────────────

def test_manual_report():
    payload = {
        "lat": 18.9500,
        "lon": 72.8200,
        "severity": "high",
        "description": "Large pothole near bus stop",
    }
    resp = client.post("/manual_report", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_new"] is True
    assert data["severity"] == "high"


# ── Mock CPGRAMS ─────────────────────────────────────────────────

def test_mock_cpgrams_submit():
    payload = {
        "title": "Test Pothole",
        "description": "Test description",
        "latitude": 19.076,
        "longitude": 72.877,
        "risk_score": 85,
        "attachments": [],
    }
    resp = client.post("/mock/cpgrams/grievance", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ticket_id"].startswith("CPGRAMS-")
    assert data["status"] == "Registered"


def test_mock_cpgrams_status():
    # Submit first
    payload = {
        "title": "Test", "description": "Desc",
        "latitude": 19.076, "longitude": 72.877,
        "risk_score": 85, "attachments": [],
    }
    r = client.post("/mock/cpgrams/grievance", json=payload)
    tid = r.json()["ticket_id"]

    # Query status
    resp = client.get(f"/mock/cpgrams/status/{tid}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "Registered"


def test_mock_cpgrams_list():
    resp = client.get("/mock/cpgrams/tickets")
    assert resp.status_code == 200
