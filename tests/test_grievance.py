"""Tests for grievance filing and risk scoring."""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.services.risk_scoring import estimate_severity, compute_risk_score
from backend.models import CpgramsPayload


# ── Severity estimation ──────────────────────────────────────────

def test_severity_low():
    # Small bbox relative to frame
    assert estimate_severity([300, 200, 320, 215], 640, 480) == "low"

def test_severity_medium():
    assert estimate_severity([200, 150, 340, 260], 640, 480) == "medium"

def test_severity_high():
    assert estimate_severity([100, 100, 350, 300], 640, 480) == "high"

def test_severity_critical():
    assert estimate_severity([50, 50, 500, 400], 640, 480) == "critical"

def test_severity_empty_bbox():
    assert estimate_severity([], 640, 480) == "low"


# ── Risk score ───────────────────────────────────────────────────

def test_risk_score_range():
    score = compute_risk_score("medium", 0.9, 0.5)
    assert 0 <= score <= 100

def test_risk_score_critical_high_conf():
    score = compute_risk_score("critical", 0.95, 0.8)
    assert score >= 80, "Critical + high confidence should exceed threshold"

def test_risk_score_low_stays_low():
    score = compute_risk_score("low", 0.3, 0.2)
    assert score < 40


# ── CPGRAMS payload ──────────────────────────────────────────────

def test_cpgrams_payload_structure():
    from backend.services.grievance import build_cpgrams_payload
    payload = build_cpgrams_payload(
        pothole_id=42,
        lat=19.076,
        lon=72.877,
        severity="critical",
        risk_score=92,
        snapshot_b64="abc123",
    )
    assert isinstance(payload, CpgramsPayload)
    assert "critical" in payload.title.lower() or "Critical" in payload.title
    assert payload.latitude == 19.076
    assert payload.risk_score == 92
    assert len(payload.attachments) == 1
