"""Database engine, session, and table definitions."""

import os
import sys
from datetime import datetime, timezone
from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Boolean, Text,
    DateTime, JSON, ForeignKey, event, inspect
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

# ── Resolve project root so `config` is importable ──────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import settings

DATABASE_URL = settings.database_url
_is_sqlite = DATABASE_URL.startswith("sqlite")

# ── Engine setup ────────────────────────────────────────────────────────
if _is_sqlite:
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _load_spatialite(dbapi_conn, _):
        """Try to load SpatiaLite; fall back gracefully if not available."""
        dbapi_conn.enable_load_extension(True)
        for lib in ("mod_spatialite", "libspatialite"):
            try:
                dbapi_conn.load_extension(lib)
                return
            except Exception:
                pass
        # SpatiaLite not available – spatial queries will use plain lat/lon
else:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# ── ORM Models ──────────────────────────────────────────────────────────

class DefectRegistry(Base):
    """A unique pothole record (spatially deduplicated)."""
    __tablename__ = "defect_registry"

    pothole_id = Column(Integer, primary_key=True, index=True)
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)
    first_seen = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_seen = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    severity = Column(String(20), default="low")           # low | medium | high | critical
    risk_score = Column(Float, default=0.0)
    is_repaired = Column(Boolean, default=False)
    avg_confidence = Column(Float, default=0.0)
    detection_count = Column(Integer, default=1)
    snapshots = Column(JSON, default=list)                  # list of snapshot URLs
    description = Column(Text, default="")
    latest_ultrasonic_distance_cm = Column(Float, nullable=True)
    estimated_depth_cm = Column(Float, nullable=True)
    sensor_fusion_score = Column(Float, nullable=True)
    sensor_source = Column(String(50), default="")
    sensor_samples_cm = Column(JSON, default=list)

    # Relationships
    grievances = relationship("GrievanceLifecycle", back_populates="pothole")


class GrievanceLifecycle(Base):
    """Tracks grievance filed for a pothole."""
    __tablename__ = "grievance_lifecycle"

    id = Column(Integer, primary_key=True, index=True)
    pothole_id = Column(Integer, ForeignKey("defect_registry.pothole_id"), nullable=False)
    grievance_system = Column(String(50), default="CPGRAMS")
    grievance_id = Column(String(100))                      # ticket ID returned by portal
    status = Column(String(50), default="Pending")          # Pending | Registered | Under Review | Resolved | Appealed
    submitted_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    sla_deadline = Column(DateTime(timezone=True), nullable=True)
    payload = Column(JSON, default=dict)                    # full payload sent

    pothole = relationship("DefectRegistry", back_populates="grievances")


# ── Create all tables ───────────────────────────────────────────────────

def init_db():
    """Create tables if they don't exist."""
    Base.metadata.create_all(bind=engine)
    _ensure_hackathon_columns()


def _ensure_hackathon_columns():
    """Add newer demo columns to existing deployments without Alembic."""
    columns = {
        "latest_ultrasonic_distance_cm": "FLOAT",
        "estimated_depth_cm": "FLOAT",
        "sensor_fusion_score": "FLOAT",
        "sensor_source": "VARCHAR(50) DEFAULT ''",
        "sensor_samples_cm": "JSON",
    }

    with engine.begin() as conn:
        existing = {
            column_info["name"]
            for column_info in inspect(conn).get_columns("defect_registry")
        }
        for name, sql_type in columns.items():
            if name not in existing:
                conn.exec_driver_sql(
                    f"ALTER TABLE defect_registry ADD COLUMN {name} {sql_type}"
                )


def get_db():
    """FastAPI dependency – yields a DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
