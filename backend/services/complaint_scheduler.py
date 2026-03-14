"""Cluster potholes and file complaints on a fixed cadence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Iterable, cast

from sqlalchemy.orm import Session

from backend.database import ComplaintRegistry, DefectRegistry
from backend.services.dedup import haversine_meters
from backend.services.grievance import build_cpgrams_payload, file_grievance
from config import settings


@dataclass
class Cluster:
    key: str
    center_lat: float
    center_lon: float
    potholes: list[DefectRegistry]


def _cluster_key(lat: float, lon: float) -> str:
    return f"{lat:.5f}:{lon:.5f}"


def cluster_potholes(potholes: Iterable[DefectRegistry], radius_m: float) -> list[Cluster]:
    remaining = list(potholes)
    clusters: list[Cluster] = []

    while remaining:
        seed = remaining.pop(0)
        group = [seed]
        i = 0
        while i < len(remaining):
            candidate = remaining[i]
            seed_lat = float(cast(float, seed.lat))
            seed_lon = float(cast(float, seed.lon))
            cand_lat = float(cast(float, candidate.lat))
            cand_lon = float(cast(float, candidate.lon))
            if haversine_meters(seed_lat, seed_lon, cand_lat, cand_lon) <= radius_m:
                group.append(candidate)
                remaining.pop(i)
                continue
            i += 1

        center_lat = sum(float(cast(float, p.lat)) for p in group) / len(group)
        center_lon = sum(float(cast(float, p.lon)) for p in group) / len(group)
        clusters.append(Cluster(
            key=_cluster_key(center_lat, center_lon),
            center_lat=center_lat,
            center_lon=center_lon,
            potholes=group,
        ))

    return clusters


def _severity_rank(severity: str) -> int:
    return {"low": 0, "medium": 1, "high": 2, "critical": 3}.get(severity, 0)


async def run_complaint_cycle(db: Session) -> list[ComplaintRegistry]:
    now = datetime.now(timezone.utc)
    active = db.query(DefectRegistry).filter(DefectRegistry.is_repaired == False).all()
    clusters = cluster_potholes(active, settings.cluster_radius_m)
    results: list[ComplaintRegistry] = []

    for cluster in clusters:
        total_detections = sum(int(cast(int, p.detection_count)) for p in cluster.potholes)
        max_sev = max(cluster.potholes, key=lambda p: _severity_rank(str(cast(str, p.severity)))).severity

        if total_detections < settings.cluster_min_detections:
            continue
        max_sev_str = str(cast(str, max_sev))
        if _severity_rank(max_sev_str) < _severity_rank(settings.cluster_min_severity):
            continue

        existing = (
            db.query(ComplaintRegistry)
            .filter(ComplaintRegistry.cluster_key == cluster.key)
            .order_by(ComplaintRegistry.last_filed_at.desc())
            .first()
        )

        if existing is not None:
            expires_at = cast(datetime | None, existing.expires_at)
            if expires_at and expires_at > now:
                results.append(existing)
                continue

        representative = max(cluster.potholes, key=lambda p: float(cast(float, p.risk_score)))
        payload = build_cpgrams_payload(
            int(cast(int, representative.pothole_id)),
            cluster.center_lat,
            cluster.center_lon,
            str(max_sev),
            float(cast(float, representative.risk_score)),
            None,
        )
        payload.title = f"Cluster pothole hazard ({len(cluster.potholes)} reports)"
        payload.description += (
            f"\nCluster center: ({cluster.center_lat:.6f}, {cluster.center_lon:.6f})"
            f"\nCluster size : {len(cluster.potholes)} potholes"
            f"\nDetections   : {total_detections}"
        )

        ticket_id = await file_grievance(db, int(cast(int, representative.pothole_id)), payload, settings.cpgrams_endpoint)

        expires_at = now + timedelta(days=settings.complaint_expiry_days)
        record = ComplaintRegistry(
            cluster_key=cluster.key,
            center_lat=cluster.center_lat,
            center_lon=cluster.center_lon,
            pothole_count=len(cluster.potholes),
            max_severity=max_sev,
            status="Active",
            authority=payload.title,
            last_filed_at=now,
            expires_at=expires_at,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        results.append(record)

    return results


def run_complaint_cycle_sync(db: Session) -> list[ComplaintRegistry]:
    """Sync wrapper for background scheduling."""
    import asyncio
    return asyncio.run(run_complaint_cycle(db))
