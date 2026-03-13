"""Manual report router — citizens can upload a photo + pin location."""

from __future__ import annotations

import base64
import uuid
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.database import DefectRegistry, get_db
from backend.models import ManualReportRequest, DetectionResponse
from backend.services.dedup import find_nearby_pothole
from backend.services.risk_scoring import compute_risk_score
from config import settings

router = APIRouter(tags=["manual-report"])


@router.post("/manual_report", response_model=DetectionResponse)
def manual_report(req: ManualReportRequest, db: Session = Depends(get_db)):
    """Accept a manual pothole report from a citizen / dashboard."""

    # Save snapshot
    snap_url = None
    if req.snapshot_base64:
        fname = f"{uuid.uuid4().hex}.jpg"
        fpath = os.path.join(settings.storage_path, fname)
        with open(fpath, "wb") as f:
            f.write(base64.b64decode(req.snapshot_base64))
        snap_url = f"/snapshots/{fname}"

    risk = compute_risk_score(req.severity, confidence=0.7)

    # Dedup
    existing = find_nearby_pothole(db, req.lat, req.lon, settings.dedup_radius_meters)
    if existing:
        existing.last_seen = datetime.now(timezone.utc)
        existing.detection_count += 1
        if snap_url:
            snaps = existing.snapshots or []
            snaps.append(snap_url)
            existing.snapshots = snaps
        if req.description:
            existing.description = req.description
        db.commit()
        db.refresh(existing)
        return DetectionResponse(
            pothole_id=existing.pothole_id,
            is_new=False,
            severity=existing.severity,
            risk_score=existing.risk_score,
        )

    pothole = DefectRegistry(
        lat=req.lat,
        lon=req.lon,
        severity=req.severity,
        risk_score=risk,
        avg_confidence=0.7,
        snapshots=[snap_url] if snap_url else [],
        description=req.description,
    )
    db.add(pothole)
    db.commit()
    db.refresh(pothole)

    return DetectionResponse(
        pothole_id=pothole.pothole_id,
        is_new=True,
        severity=pothole.severity,
        risk_score=pothole.risk_score,
    )
