"""Geospatial deduplication service.

Uses the Haversine formula to find existing potholes within a radius
(default 2.5 m).  Works with plain lat/lon columns so it runs on both
SQLite and PostGIS without requiring spatial extensions.
"""

import math
from sqlalchemy.orm import Session
from backend.database import DefectRegistry


def haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return distance in metres between two WGS‑84 points."""
    R = 6_371_000  # Earth radius in metres
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def find_nearby_pothole(
    db: Session,
    lat: float,
    lon: float,
    radius_m: float = 2.5,
) -> DefectRegistry | None:
    """Return the closest pothole within *radius_m* metres, or None."""
    # Bounding‑box pre‑filter (≈ 0.001° ≈ 111 m)
    deg_margin = radius_m / 111_000 * 2  # generous overselect
    candidates = (
        db.query(DefectRegistry)
        .filter(
            DefectRegistry.lat.between(lat - deg_margin, lat + deg_margin),
            DefectRegistry.lon.between(lon - deg_margin, lon + deg_margin),
            DefectRegistry.is_repaired == False,
        )
        .all()
    )
    best, best_dist = None, float("inf")
    for p in candidates:
        d = haversine_meters(lat, lon, p.lat, p.lon)
        if d < radius_m and d < best_dist:
            best, best_dist = p, d
    return best
