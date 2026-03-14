"""Detections router — ingest edge detections, run live inference, list results."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.database import DefectRegistry, get_db
from backend.models import (
    DetectionRequest,
    DetectionResponse,
    GrievanceOut,
    LiveFrameDetection,
    LiveFrameRequest,
    LiveFrameResponse,
    PotholeDetail,
    PotholeOut,
)
from backend.services.detection_ingest import ingest_detection
from backend.services.dedup import find_nearby_pothole
from backend.services.live_detection import decode_frame, get_detector

router = APIRouter(tags=["detections"])


@router.post("/detections", response_model=DetectionResponse)
async def post_detection(req: DetectionRequest, db: Session = Depends(get_db)):
    """Receive a detection from an edge device."""
    return await ingest_detection(req, db)


@router.post("/live/detect", response_model=LiveFrameResponse)
async def detect_live_frame(req: LiveFrameRequest, db: Session = Depends(get_db)):
    """Run pothole inference on a single browser-captured frame."""
    try:
        frame = decode_frame(req.image_base64)
        detector = get_detector()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Detector unavailable: {exc}") from exc

    frame_h, frame_w = frame.shape[:2]
    detections = detector.detect_image(frame, req.camera_id, req.lat, req.lon)
    response_items: list[LiveFrameDetection] = []

    for detection in detections:
        pothole_id = None
        risk_score = None
        is_new = None
        if req.persist:
            result = await ingest_detection(DetectionRequest(**detection), db)
            pothole_id = result.pothole_id
            risk_score = result.risk_score
            is_new = result.is_new

        response_items.append(
            LiveFrameDetection(
                bbox=detection.get("bbox", []),
                confidence=detection.get("confidence", 0.0),
                severity_est=detection.get("severity_est"),
                class_name=detection.get("class_name", "pothole"),
                pothole_id=pothole_id,
                risk_score=risk_score,
                is_new=is_new,
                ultrasonic_distance_cm=detection.get("ultrasonic_distance_cm"),
                estimated_depth_cm=detection.get("estimated_depth_cm"),
                sensor_fusion_score=detection.get("sensor_fusion_score"),
                sensor_source=detection.get("sensor_source"),
                vibration_rms_g=detection.get("vibration_rms_g"),
                peak_accel_g=detection.get("peak_accel_g"),
                shock_index=detection.get("shock_index"),
                roughness_index=detection.get("roughness_index"),
                speed_kph=detection.get("speed_kph"),
                pitch_deg=detection.get("pitch_deg"),
                roll_deg=detection.get("roll_deg"),
                yaw_deg=detection.get("yaw_deg"),
            )
        )

    return LiveFrameResponse(
        detections=response_items,
        processed_at=datetime.now(timezone.utc).isoformat(),
        frame_width=frame_w,
        frame_height=frame_h,
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
        raise HTTPException(404, "Pothole not found")
    grievances = [GrievanceOut.model_validate(g) for g in p.grievances]
    out = PotholeOut.model_validate(p).model_dump()
    out["grievances"] = grievances
    return PotholeDetail(**out)
