"""FastAPI application — Autonomous Pothole Detection & Reporting."""

from __future__ import annotations

import os
import sys
import logging
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Ensure project root is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.database import init_db, SessionLocal
from backend.routers import detections, manual_report, verification, mock_cpgrams, stream, telemetry, complaints
from backend.services.complaint_scheduler import run_complaint_cycle
from config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ── Lifespan ────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing database…")
    init_db()
    logger.info("Database ready. Storage: %s", settings.storage_path)

    stop_event = threading.Event()

    def _complaint_loop():
        while not stop_event.is_set():
            try:
                db = SessionLocal()
                try:
                    import asyncio
                    asyncio.run(run_complaint_cycle(db))
                finally:
                    db.close()
            except Exception as exc:
                logger.error("Complaint scheduler error: %s", exc)
            stop_event.wait(settings.complaint_interval_hours * 3600)

    thread = threading.Thread(target=_complaint_loop, daemon=True)
    thread.start()
    yield
    stop_event.set()


# ── App ─────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Pothole Detection & Reporting API",
    version="1.0.0",
    description="Autonomous pothole detection with closed-loop grievance filing.",
    lifespan=lifespan,
)

# CORS — allow everything for hackathon dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health (must be registered BEFORE catch-all static mount) ───────────

@app.get("/health", tags=["system"])
def health():
    return {"status": "ok"}


# ── Routers ─────────────────────────────────────────────────────────────

app.include_router(detections.router)
app.include_router(manual_report.router)
app.include_router(verification.router)
app.include_router(mock_cpgrams.router)
app.include_router(stream.router)
app.include_router(telemetry.router)
app.include_router(complaints.router)

# ── Static files ────────────────────────────────────────────────────────

# Serve saved snapshots
os.makedirs(settings.storage_path, exist_ok=True)
app.mount("/snapshots", StaticFiles(directory=settings.storage_path), name="snapshots")

# Serve frontend (catch-all — must be LAST)
frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.isdir(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
