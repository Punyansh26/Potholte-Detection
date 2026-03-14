"""Tests for phone/IP camera source handling in the edge client."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from detector.edge_client import _build_ip_webcam_candidates


def test_ip_webcam_candidates_for_video_endpoint_include_snapshot_fallback():
    candidates = _build_ip_webcam_candidates("http://192.168.1.25:8080/video")
    assert ("stream", "http://192.168.1.25:8080/video") in candidates
    assert ("snapshot", "http://192.168.1.25:8080/shot.jpg") in candidates


def test_ip_webcam_candidates_for_root_include_common_endpoints():
    candidates = _build_ip_webcam_candidates("http://192.168.1.25:8080")
    assert ("stream", "http://192.168.1.25:8080/video") in candidates
    assert ("stream", "http://192.168.1.25:8080/videofeed") in candidates
    assert ("snapshot", "http://192.168.1.25:8080/shot.jpg") in candidates