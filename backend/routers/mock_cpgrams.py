"""Mock CPGRAMS endpoint — simulates the government grievance portal."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Dict

from fastapi import APIRouter
from backend.models import CpgramsPayload, CpgramsResponse

router = APIRouter(prefix="/mock/cpgrams", tags=["mock-cpgrams"])

# In-memory ticket store for the mock
_tickets: Dict[str, dict] = {}


@router.post("/grievance", response_model=CpgramsResponse)
def submit_grievance(payload: CpgramsPayload):
    """Simulate CPGRAMS grievance submission. Returns a ticket ID."""
    ticket_id = f"CPGRAMS-{uuid.uuid4().hex[:8].upper()}"
    _tickets[ticket_id] = {
        "status": "Registered",
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "payload": payload.model_dump(),
    }
    return CpgramsResponse(ticket_id=ticket_id, status="Registered")


@router.get("/status/{ticket_id}")
def get_ticket_status(ticket_id: str):
    """Return the mock status of a grievance ticket."""
    if ticket_id not in _tickets:
        return {"error": "Ticket not found", "ticket_id": ticket_id}
    return {
        "ticket_id": ticket_id,
        **_tickets[ticket_id],
    }


@router.put("/status/{ticket_id}")
def update_ticket_status(ticket_id: str, status: str):
    """Manually update ticket status (for demo purposes)."""
    if ticket_id not in _tickets:
        return {"error": "Ticket not found"}
    _tickets[ticket_id]["status"] = status
    return {"ticket_id": ticket_id, "status": status}


@router.get("/tickets")
def list_tickets():
    """List all mock tickets."""
    return _tickets
