"""Detections router — ingest edge detections, deduplicate, score, auto-file."""

from __future__ import annotations

import base64
import uuid
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.database import DefectRegistry, get_db
from backend.models import DetectionRequest, DetectionResponse, PotholeOut, PotholeDetail, GrievanceOut
from backend.services.dedup import find_nearby_pothole
from backend.services.risk_scoring import estimate_severity, compute_risk_score
from backend.services.grievance import build_cpgrams_payload, file_grievance
from config import settings

router = APIRouter(tags=["detections"])


def _save_snapshot(snapshot_b64: str | None) -> str | None:
    """Persist a base64 snapshot to disk, return relative URL."""
    if not snapshot_b64:
        return None
    fname = f"{uuid.uuid4().hex}.jpg"
    fpath = os.path.join(settings.storage_path, fname)
    with open(fpath, "wb") as f:
        f.write(base64.b64decode(snapshot_b64))
    return f"/snapshots/{fname}"


@router.post("/detections", response_model=DetectionResponse)
async def post_detection(req: DetectionRequest, db: Session = Depends(get_db)):
    """Receive a detection from an edge device."""

    # 1. Severity & risk
    severity = req.severity_est or estimate_severity(req.bbox)
    risk = compute_risk_score(severity, req.confidence)

    # 2. Save snapshot
    snap_url = _save_snapshot(req.snapshot_base64)

    # 3. Spatial dedup
    existing = find_nearby_pothole(db, req.lat, req.lon, settings.dedup_radius_meters)

    if existing:
        # Update existing record
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
        # Upgrade severity if new detection is worse
        sev_order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
        if sev_order.get(severity, 0) > sev_order.get(existing.severity, 0):
            existing.severity = severity
        existing.risk_score = max(existing.risk_score, risk)
        db.commit()
        db.refresh(existing)
        pothole = existing
        is_new = False
    else:
        # Create new record
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

    # 4. Auto-file grievance if critical
    grievance_filed = False
    grievance_id = None
    if risk >= settings.risk_threshold:
        payload = build_cpgrams_payload(
            pothole.pothole_id, req.lat, req.lon,
            severity, risk, req.snapshot_base64,
        )
        grievance_id = await file_grievance(db, pothole.pothole_id, payload, settings.cpgrams_endpoint)
        grievance_filed = grievance_id is not None

    return DetectionResponse(
        pothole_id=pothole.pothole_id,
        is_new=is_new,
        severity=pothole.severity,
        risk_score=pothole.risk_score,
        grievance_filed=grievance_filed,
        grievance_id=grievance_id,
    )


@router.get("/potholes", response_model=list[PotholeOut])
def list_potholes(
    severity: str | None = Query(None),
    repaired: bool | None = Query(None),
    min_lat: float | None = Query(None),
    max_lat: float | None = Query(None),
    min_lon: float | None = Query(None),
    max_lon: float | None = Query(None),
    db: Session = Depends(get_db),
):
    """List potholes with optional filters."""
    q = db.query(DefectRegistry)
    if severity:
        q = q.filter(DefectRegistry.severity == severity)
    if repaired is not None:
        q = q.filter(DefectRegistry.is_repaired == repaired)
    if min_lat is not None:
        q = q.filter(DefectRegistry.lat >= min_lat)
    if max_lat is not None:
        q = q.filter(DefectRegistry.lat <= max_lat)
    if min_lon is not None:
        q = q.filter(DefectRegistry.lon >= min_lon)
    if max_lon is not None:
        q = q.filter(DefectRegistry.lon <= max_lon)
    rows = q.order_by(DefectRegistry.last_seen.desc()).all()
    return [PotholeOut.model_validate(r) for r in rows]


@router.get("/potholes/{pothole_id}", response_model=PotholeDetail)
def get_pothole(pothole_id: int, db: Session = Depends(get_db)):
    """Get full detail for a single pothole."""
    p = db.query(DefectRegistry).filter_by(pothole_id=pothole_id).first()
    if not p:
        from fastapi import HTTPException
        raise HTTPException(404, "Pothole not found")
    grievances = [GrievanceOut.model_validate(g) for g in p.grievances]
    out = PotholeOut.model_validate(p).model_dump()
    out["grievances"] = grievances
    return PotholeDetail(**out)
