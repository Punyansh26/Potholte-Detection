"""Shared detection ingestion helpers."""

from __future__ import annotations

import base64
import os
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.database import DefectRegistry
from backend.models import DetectionRequest, DetectionResponse
from backend.services.dedup import find_nearby_pothole
from backend.services.grievance import build_cpgrams_payload, file_grievance
from backend.services.risk_scoring import compute_risk_score, estimate_severity
from config import settings


def save_snapshot(snapshot_b64: str | None) -> str | None:
    """Persist a base64 snapshot to disk and return the relative URL."""
    if not snapshot_b64:
        return None
    fname = f"{uuid.uuid4().hex}.jpg"
    fpath = os.path.join(settings.storage_path, fname)
    with open(fpath, "wb") as file_obj:
        file_obj.write(base64.b64decode(snapshot_b64))
    return f"/snapshots/{fname}"


async def ingest_detection(req: DetectionRequest, db: Session) -> DetectionResponse:
    """Deduplicate, persist, and optionally auto-file a grievance."""
    severity = req.severity_est or estimate_severity(req.bbox)
    risk = compute_risk_score(severity, req.confidence)
    snap_url = save_snapshot(req.snapshot_base64)

    existing = find_nearby_pothole(db, req.lat, req.lon, settings.dedup_radius_meters)

    if existing:
        existing.last_seen = datetime.now(timezone.utc)
        existing.detection_count += 1
        existing.avg_confidence = (
            (existing.avg_confidence * (existing.detection_count - 1) + req.confidence)
            / existing.detection_count
        )
        if snap_url:
            snaps = existing.snapshots or []
            snaps.append(snap_url)
            existing.snapshots = snaps
        sev_order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
        if sev_order.get(severity, 0) > sev_order.get(existing.severity, 0):
            existing.severity = severity
        existing.risk_score = max(existing.risk_score, risk)
        db.commit()
        db.refresh(existing)
        pothole = existing
        is_new = False
    else:
        pothole = DefectRegistry(
            lat=req.lat,
            lon=req.lon,
            severity=severity,
            risk_score=risk,
            avg_confidence=req.confidence,
            snapshots=[snap_url] if snap_url else [],
        )
        db.add(pothole)
        db.commit()
        db.refresh(pothole)
        is_new = True

    grievance_filed = False
    grievance_id = None
    if risk >= settings.risk_threshold:
        payload = build_cpgrams_payload(
            pothole.pothole_id,
            req.lat,
            req.lon,
            severity,
            risk,
            req.snapshot_base64,
        )
        grievance_id = await file_grievance(
            db,
            pothole.pothole_id,
            payload,
            settings.cpgrams_endpoint,
        )
        grievance_filed = grievance_id is not None

    return DetectionResponse(
        pothole_id=pothole.pothole_id,
        is_new=is_new,
        severity=pothole.severity,
        risk_score=pothole.risk_score,
        grievance_filed=grievance_filed,
        grievance_id=grievance_id,
    )