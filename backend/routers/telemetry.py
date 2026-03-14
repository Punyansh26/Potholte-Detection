"""Phone telemetry ingestion and latest status."""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.database import SensorEvent, get_db
from backend.models import (
    DetectionRequest,
    TelemetryIngestRequest,
    TelemetryIngestResponse,
    SensorEventOut,
    LiveSensorTelemetry,
)
from backend.services.detection_ingest import ingest_detection
from backend.services.phone_telemetry import get_latest, set_latest
from backend.services.sensor_classifier import classify_pothole, build_telemetry_view
from typing import cast

router = APIRouter(prefix="/telemetry", tags=["telemetry"])


def _as_float(value) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _as_int(value) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


async def _fetch_snapshot_b64(image_url: str | None) -> str | None:
    if not image_url:
        return None
    try:
        import base64
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(image_url)
            resp.raise_for_status()
            return base64.b64encode(resp.content).decode("ascii")
    except Exception:
        return None


@router.post("/ingest", response_model=TelemetryIngestResponse)
async def ingest_telemetry(req: TelemetryIngestRequest, db: Session = Depends(get_db)):
    payload = req.model_dump()
    model_result = classify_pothole(payload)
    model_score = float(model_result.get("score") or 0.0)
    is_pothole = bool(model_result.get("is_pothole"))
    if req.vision_detected and (req.vision_confidence or 0) >= 0.5:
        is_pothole = True
    timestamp = req.timestamp or datetime.now(timezone.utc).isoformat()

    event = SensorEvent(
        device_id=req.device_id,
        captured_at=datetime.now(timezone.utc),
        lat=req.lat,
        lon=req.lon,
        speed_kph=req.speed_kph,
        accel_x=req.accel_x,
        accel_y=req.accel_y,
        accel_z=req.accel_z,
        gyro_pitch=req.gyro_pitch,
        gyro_roll=req.gyro_roll,
        gyro_yaw=req.gyro_yaw,
        vision_detected=bool(req.vision_detected) if req.vision_detected is not None else False,
        vision_confidence=req.vision_confidence,
        image_url=req.image_url,
        raw_payload=payload,
        model_score=model_score,
        classified_pothole=is_pothole,
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    set_latest({**payload, "timestamp": timestamp, "model_score": model_score})
    telemetry_view = build_telemetry_view({**payload, "timestamp": timestamp}, model_score)

    linked_id = None
    if is_pothole and req.lat is not None and req.lon is not None:
        snapshot_b64 = await _fetch_snapshot_b64(req.image_url)

        if model_score >= 0.8:
            severity_est = "high"
        elif model_score >= 0.6:
            severity_est = "medium"
        else:
            severity_est = "low"

        detection = DetectionRequest(
            camera_id=req.device_id,
            timestamp=timestamp,
            lat=req.lat,
            lon=req.lon,
            bbox=[],
            confidence=req.vision_confidence or model_score,
            severity_est=severity_est,
            snapshot_base64=snapshot_b64,
            sensor_source=req.device_id,
            speed_kph=req.speed_kph,
            pitch_deg=req.gyro_pitch,
            roll_deg=req.gyro_roll,
            yaw_deg=req.gyro_yaw,
            vibration_rms_g=_as_float(telemetry_view.get("vibration_rms_g")),
            peak_accel_g=_as_float(telemetry_view.get("peak_accel_g")),
            shock_index=_as_int(telemetry_view.get("shock_index")),
            roughness_index=_as_float(telemetry_view.get("roughness_index")),
        )
        result = await ingest_detection(detection, db)
        linked_id = result.pothole_id
        setattr(event, "linked_pothole_id", linked_id)
        db.commit()

    return TelemetryIngestResponse(
        event_id=int(cast(int, event.id)),
        classified_pothole=is_pothole,
        model_score=model_score,
        linked_pothole_id=linked_id,
    )


@router.get("/latest", response_model=LiveSensorTelemetry)
def latest_telemetry():
    payload = get_latest() or {}
    model_score = payload.get("model_score") if isinstance(payload, dict) else None
    view = build_telemetry_view(payload, model_score)
    return LiveSensorTelemetry.model_validate(view)


@router.get("/events", response_model=list[SensorEventOut])
def list_events(limit: int = Query(default=50, ge=1, le=500), db: Session = Depends(get_db)):
    rows = db.query(SensorEvent).order_by(SensorEvent.captured_at.desc()).limit(limit).all()
    return [SensorEventOut.model_validate(r) for r in rows]
