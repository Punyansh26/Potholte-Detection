"""FastAPI application — Autonomous Pothole Detection & Reporting."""

from __future__ import annotations

import os
import sys
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Ensure project root is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.database import init_db
from backend.routers import detections, manual_report, verification, mock_cpgrams, stream
from config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ── Lifespan ────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing database…")
    init_db()
    logger.info("Database ready. Storage: %s", settings.storage_path)
    yield


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

# ── Static files ────────────────────────────────────────────────────────

# Serve saved snapshots
os.makedirs(settings.storage_path, exist_ok=True)
app.mount("/snapshots", StaticFiles(directory=settings.storage_path), name="snapshots")

# Serve frontend (catch-all — must be LAST)
frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.isdir(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
