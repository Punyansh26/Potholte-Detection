"""Verification router — re-image a pothole to check repair status."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.database import DefectRegistry, GrievanceLifecycle, get_db
from backend.models import VerificationRequest, VerificationResponse
from backend.services.verification import is_repaired

router = APIRouter(tags=["verification"])


@router.put("/potholes/{pothole_id}/verify", response_model=VerificationResponse)
def verify_pothole(
    pothole_id: int,
    req: VerificationRequest,
    db: Session = Depends(get_db),
):
    """Compare a new snapshot against existing ones for repair verification."""
    pothole = db.query(DefectRegistry).filter_by(pothole_id=pothole_id).first()
    if not pothole:
        raise HTTPException(404, "Pothole not found")

    previous_status = "repaired" if pothole.is_repaired else "active"

    # Get the most recent previous snapshot (base64 from disk)
    old_b64 = None
    if pothole.snapshots:
        import base64, os
        last_snap = pothole.snapshots[-1]  # e.g. "/snapshots/abc.jpg"
        fname = last_snap.split("/")[-1]
        fpath = os.path.join("storage", "snapshots", fname)
        if os.path.exists(fpath):
            with open(fpath, "rb") as f:
                old_b64 = base64.b64encode(f.read()).decode()

    repaired, similarity, action = is_repaired(req.snapshot_base64, old_b64)

    if repaired:
        pothole.is_repaired = True
        action = "marked_repaired"
        new_status = "repaired"
    else:
        new_status = "active"
        # Check if any grievance was marked Closed/Resolved
        closed_grievances = (
            db.query(GrievanceLifecycle)
            .filter_by(pothole_id=pothole_id)
            .filter(GrievanceLifecycle.status.in_(["Resolved", "Closed"]))
            .all()
        )
        if closed_grievances:
            # Auto-escalate: the portal says fixed but it's not
            for g in closed_grievances:
                g.status = "Appealed"
            action = "escalated"
            new_status = "escalated"

    db.commit()
    db.refresh(pothole)

    return VerificationResponse(
        pothole_id=pothole_id,
        previous_status=previous_status,
        new_status=new_status,
        similarity_score=similarity,
        action_taken=action,
    )
