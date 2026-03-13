"""Grievance filing service — builds CPGRAMS payloads and POSTs them."""

from __future__ import annotations

import httpx
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session

from backend.database import GrievanceLifecycle
from backend.models import CpgramsPayload

logger = logging.getLogger(__name__)


def build_cpgrams_payload(
    pothole_id: int,
    lat: float,
    lon: float,
    severity: str,
    risk_score: float,
    snapshot_b64: str | None = None,
) -> CpgramsPayload:
    """Construct the government-formatted complaint payload."""
    depth_est = {"low": "~2cm", "medium": "~5cm", "high": "~10cm", "critical": "~15cm+"}.get(severity, "unknown")
    return CpgramsPayload(
        title=f"Pothole — {severity.capitalize()}: {depth_est} deep — ID #{pothole_id}",
        description=(
            f"Automated pothole detection report.\n"
            f"  Location : ({lat:.6f}, {lon:.6f})\n"
            f"  Severity : {severity}\n"
            f"  Risk Score: {risk_score}\n"
            f"  Detection : {datetime.now(timezone.utc).isoformat()}\n"
            f"  System    : Autonomous Pothole Detection v1.0"
        ),
        latitude=lat,
        longitude=lon,
        risk_score=risk_score,
        attachments=[snapshot_b64] if snapshot_b64 else [],
    )


async def file_grievance(
    db: Session,
    pothole_id: int,
    payload: CpgramsPayload,
    endpoint: str,
) -> str | None:
    """POST payload to CPGRAMS (or mock) and persist the ticket."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(endpoint, json=payload.model_dump())
            resp.raise_for_status()
            data = resp.json()
        ticket_id = data.get("ticket_id", "UNKNOWN")
    except Exception as exc:
        logger.error("Grievance filing failed for pothole %s: %s", pothole_id, exc)
        ticket_id = None

    record = GrievanceLifecycle(
        pothole_id=pothole_id,
        grievance_system="CPGRAMS",
        grievance_id=ticket_id,
        status="Registered" if ticket_id else "Failed",
        sla_deadline=datetime.now(timezone.utc) + timedelta(days=15),
        payload=payload.model_dump(),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return ticket_id
