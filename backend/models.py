"""Pydantic request / response schemas."""

from __future__ import annotations
from datetime import datetime
from typing import Any, List, Optional
from pydantic import BaseModel, ConfigDict, Field


# ── Detection (edge client → backend) ─────────────────────────────────

class DetectionRequest(BaseModel):
    camera_id: str = "edge-001"
    timestamp: str = ""                          # ISO‑8601
    lat: float
    lon: float
    bbox: List[float] = Field(default_factory=list)  # [x_min, y_min, x_max, y_max]
    confidence: float = 0.5
    severity_est: Optional[str] = None           # auto-computed if not given
    snapshot_base64: Optional[str] = None        # base64 JPEG
    ultrasonic_distance_cm: Optional[float] = None
    estimated_depth_cm: Optional[float] = None
    sensor_fusion_score: Optional[float] = None
    sensor_source: Optional[str] = None
    sensor_samples_cm: List[float] = Field(default_factory=list)
    vibration_rms_g: Optional[float] = None
    peak_accel_g: Optional[float] = None
    shock_index: Optional[int] = None
    roughness_index: Optional[float] = None
    speed_kph: Optional[float] = None
    altitude_m: Optional[float] = None
    pitch_deg: Optional[float] = None
    roll_deg: Optional[float] = None
    yaw_deg: Optional[float] = None

class DetectionResponse(BaseModel):
    pothole_id: int
    is_new: bool
    severity: str
    risk_score: float
    grievance_filed: bool = False
    grievance_id: Optional[str] = None


class LiveFrameRequest(BaseModel):
    image_base64: str
    camera_id: str = "browser-camera"
    lat: float = 0.0
    lon: float = 0.0
    persist: bool = True


class LiveFrameDetection(BaseModel):
    bbox: List[float] = Field(default_factory=list)
    confidence: float = 0.0
    severity_est: Optional[str] = None
    class_name: str = "pothole"
    pothole_id: Optional[int] = None
    risk_score: Optional[float] = None
    is_new: Optional[bool] = None
    ultrasonic_distance_cm: Optional[float] = None
    estimated_depth_cm: Optional[float] = None
    sensor_fusion_score: Optional[float] = None
    sensor_source: Optional[str] = None
    vibration_rms_g: Optional[float] = None
    peak_accel_g: Optional[float] = None
    shock_index: Optional[int] = None
    roughness_index: Optional[float] = None
    speed_kph: Optional[float] = None
    altitude_m: Optional[float] = None
    pitch_deg: Optional[float] = None
    roll_deg: Optional[float] = None
    yaw_deg: Optional[float] = None


class LiveFrameResponse(BaseModel):
    detections: List[LiveFrameDetection] = Field(default_factory=list)
    processed_at: str = ""
    frame_width: int = 0
    frame_height: int = 0


class LiveSensorTelemetry(BaseModel):
    mode: str = "vehicle"
    sensor_source: str = "demo-sensor-rig"
    captured_at: str = ""
    detection_count: int = 0
    max_severity: str = "none"
    vibration_rms_g: float = 0.0
    peak_accel_g: float = 0.0
    shock_index: int = 0
    roughness_index: float = 0.0
    speed_kph: Optional[float] = None
    altitude_m: Optional[float] = None
    pitch_deg: float = 0.0
    roll_deg: float = 0.0
    yaw_deg: float = 0.0
    ultrasonic_distance_cm: Optional[float] = None
    estimated_depth_cm: Optional[float] = None
    sensor_fusion_score: Optional[float] = None
    advisory: str = "Monitoring road surface"


class LiveTelemetryResponse(BaseModel):
    telemetry: LiveSensorTelemetry


# ── Pothole list / detail ─────────────────────────────────────────────

class PotholeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    pothole_id: int
    lat: float
    lon: float
    first_seen: Any = None
    last_seen: Any = None
    severity: str
    risk_score: float
    is_repaired: bool
    avg_confidence: float
    detection_count: int
    snapshots: list = []
    description: str = ""
    latest_ultrasonic_distance_cm: Optional[float] = None
    estimated_depth_cm: Optional[float] = None
    sensor_fusion_score: Optional[float] = None
    sensor_source: str = ""
    sensor_samples_cm: list = []
    latest_vibration_rms_g: Optional[float] = None
    latest_peak_accel_g: Optional[float] = None
    latest_shock_index: Optional[int] = None
    latest_roughness_index: Optional[float] = None
    latest_speed_kph: Optional[float] = None
    latest_altitude_m: Optional[float] = None
    latest_pitch_deg: Optional[float] = None
    latest_roll_deg: Optional[float] = None
    latest_yaw_deg: Optional[float] = None

class PotholeDetail(PotholeOut):
    grievances: List[GrievanceOut] = []


# ── Grievance ─────────────────────────────────────────────────────────

class GrievanceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    pothole_id: int
    grievance_system: str
    grievance_id: Optional[str] = None
    status: str
    submitted_at: Any = None
    sla_deadline: Any = None


# ── Manual report ─────────────────────────────────────────────────────

class ManualReportRequest(BaseModel):
    lat: float
    lon: float
    description: str = ""
    severity: str = "medium"
    snapshot_base64: Optional[str] = None


# ── Verification ──────────────────────────────────────────────────────

class VerificationRequest(BaseModel):
    snapshot_base64: str                          # new image

class VerificationResponse(BaseModel):
    pothole_id: int
    previous_status: str
    new_status: str
    similarity_score: float
    action_taken: str                             # "marked_repaired" | "escalated" | "no_change"


# ── Mock CPGRAMS ──────────────────────────────────────────────────────

class CpgramsPayload(BaseModel):
    title: str
    description: str
    latitude: float
    longitude: float
    risk_score: float
    attachments: List[str] = []                   # base64 images

class CpgramsResponse(BaseModel):
    ticket_id: str
    status: str = "Registered"
