"""Pydantic request / response schemas."""

from __future__ import annotations
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


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

class DetectionResponse(BaseModel):
    pothole_id: int
    is_new: bool
    severity: str
    risk_score: float
    grievance_filed: bool = False
    grievance_id: Optional[str] = None


# ── Pothole list / detail ─────────────────────────────────────────────

class PotholeOut(BaseModel):
    pothole_id: int
    lat: float
    lon: float
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None
    severity: str
    risk_score: float
    is_repaired: bool
    avg_confidence: float
    detection_count: int
    snapshots: list = []
    description: str = ""

    class Config:
        from_attributes = True

class PotholeDetail(PotholeOut):
    grievances: List[GrievanceOut] = []


# ── Grievance ─────────────────────────────────────────────────────────

class GrievanceOut(BaseModel):
    id: int
    pothole_id: int
    grievance_system: str
    grievance_id: Optional[str] = None
    status: str
    submitted_at: Optional[str] = None
    sla_deadline: Optional[str] = None

    class Config:
        from_attributes = True


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
