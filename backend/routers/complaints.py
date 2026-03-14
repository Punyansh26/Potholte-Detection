"""Cluster complaint execution endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.database import ComplaintRegistry, get_db
from backend.models import ComplaintOut
from backend.services.complaint_scheduler import run_complaint_cycle

router = APIRouter(prefix="/complaints", tags=["complaints"])


@router.post("/run", response_model=list[ComplaintOut])
async def run_cluster_complaints(db: Session = Depends(get_db)):
    records = await run_complaint_cycle(db)
    return [ComplaintOut.model_validate(r) for r in records]


@router.get("/summary", response_model=list[ComplaintOut])
def list_complaints(db: Session = Depends(get_db)):
    rows = db.query(ComplaintRegistry).order_by(ComplaintRegistry.last_filed_at.desc()).all()
    return [ComplaintOut.model_validate(r) for r in rows]
