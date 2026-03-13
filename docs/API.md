# API Reference

Base URL: `http://localhost:8000`

---

## Detections

### `POST /detections`
Receive a detection from an edge device. Performs spatial dedup, risk scoring, and optionally auto-files a grievance.

**Request Body:**
```json
{
  "camera_id": "edge-001",
  "timestamp": "2026-03-13T12:34:56+05:30",
  "lat": 19.0760,
  "lon": 72.8777,
  "bbox": [120, 240, 400, 540],
  "confidence": 0.92,
  "severity_est": "medium",
  "snapshot_base64": "<base64 JPEG>"
}
```

**Response:**
```json
{
  "pothole_id": 1,
  "is_new": true,
  "severity": "medium",
  "risk_score": 70.0,
  "grievance_filed": false,
  "grievance_id": null
}
```

---

### `GET /potholes`
List potholes with optional filters.

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `severity` | string | Filter: low/medium/high/critical |
| `repaired` | bool | Filter by repair status |
| `min_lat`, `max_lat` | float | Latitude bounding box |
| `min_lon`, `max_lon` | float | Longitude bounding box |

---

### `GET /potholes/{pothole_id}`
Get full detail including grievance history.

---

## Manual Report

### `POST /manual_report`
Submit a citizen-reported pothole.

**Request Body:**
```json
{
  "lat": 19.0760,
  "lon": 72.8777,
  "severity": "high",
  "description": "Large pothole near bus stop",
  "snapshot_base64": "<optional base64>"
}
```

---

## Verification

### `PUT /potholes/{pothole_id}/verify`
Compare a new image against existing snapshots to verify repair.

**Request Body:**
```json
{
  "snapshot_base64": "<base64 JPEG>"
}
```

**Response:**
```json
{
  "pothole_id": 1,
  "previous_status": "active",
  "new_status": "repaired",
  "similarity_score": 0.21,
  "action_taken": "marked_repaired"
}
```

Possible `action_taken` values: `marked_repaired`, `escalated`, `still_damaged`, `no_previous_image`

---

## Mock CPGRAMS

### `POST /mock/cpgrams/grievance`
Submit a complaint (simulated).

### `GET /mock/cpgrams/status/{ticket_id}`
Check ticket status.

### `PUT /mock/cpgrams/status/{ticket_id}?status=Resolved`
Manually update status (demo).

### `GET /mock/cpgrams/tickets`
List all mock tickets.

---

## System

### `GET /health`
Returns `{"status": "ok"}`.
