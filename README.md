# PotholeGuard — Autonomous Pothole Detection & Closed-Loop Reporting

An end-to-end prototype that **detects potholes** from camera/video, **geotags & classifies** them, **files automated grievances** to authorities (simulated CPGRAMS), and **verifies repairs** through image comparison — all on a real-time Leaflet dashboard.

## Architecture

```
┌──────────────┐     POST /detections    ┌─────────────────────┐
│  Edge Client │ ──────────────────────▶ │   FastAPI Backend   │
│  (YOLOv8)    │                         │                     │
└──────────────┘                         │  • Spatial dedup    │
                                         │  • Risk scoring     │
┌──────────────┐     POST /manual_report │  • Auto-filing      │
│  Dashboard   │ ◀─────────────────────▶ │  • Verification     │
│  (Leaflet)   │     GET /potholes       │                     │
└──────────────┘                         └─────────┬───────────┘
                                                   │
                              ┌─────────────────────┴──────────┐
                              │  SQLite/PostGIS  │  Mock CPGRAMS│
                              └──────────────────┴──────────────┘
```

## Quick Start

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Copy environment file
```bash
cp .env.example .env
```

### 3. Start the backend
```bash
python -m uvicorn backend.main:app --reload --port 8000
```

### 4. Open the dashboard
Visit **http://localhost:8000** in your browser.

### 5. Run the edge detector
```bash
# Webcam
python detector/edge_client.py --source 0

# Video file
python detector/edge_client.py --source dashcam.mp4

# Image directory
python detector/edge_client.py --source ./test_images/
```

## Docker (PostGIS)
```bash
docker-compose up -d
```

## Project Structure

```
├── backend/
│   ├── main.py              # FastAPI app
│   ├── database.py          # ORM models & DB setup
│   ├── models.py            # Pydantic schemas
│   ├── routers/
│   │   ├── detections.py    # POST /detections, GET /potholes
│   │   ├── manual_report.py # POST /manual_report
│   │   ├── verification.py  # PUT /potholes/{id}/verify
│   │   └── mock_cpgrams.py  # Simulated CPGRAMS portal
│   └── services/
│       ├── dedup.py          # Haversine spatial dedup (2.5m)
│       ├── risk_scoring.py   # Severity + risk score
│       ├── grievance.py      # CPGRAMS payload builder
│       └── verification.py   # ORB/SSIM image comparison
├── detector/
│   ├── inference.py          # YOLOv8 inference pipeline
│   ├── edge_client.py        # Edge device → backend client
│   ├── train.py              # Training script
│   └── export_onnx.py        # ONNX/TFLite export
├── frontend/
│   ├── index.html            # Dashboard SPA
│   ├── index.css             # Dark glassmorphism design
│   └── app.js                # Leaflet map + UI logic
├── privacy/
│   └── blur.py               # Face & plate blur pipeline
├── tests/                    # pytest suites
├── docs/                     # API, MODEL, PRIVACY, DEMO, TESTS
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

## Features

| Feature | Status |
|---------|--------|
| YOLOv8 pothole detection (image/video/webcam) | ✅ |
| Geospatial dedup (Haversine, 2.5m radius) | ✅ |
| Risk scoring & severity classification | ✅ |
| Auto-file grievance (simulated CPGRAMS) | ✅ |
| Repair verification (ORB/SSIM comparison) | ✅ |
| Auto-escalation when closed but still damaged | ✅ |
| Real-time Leaflet dashboard (dark theme) | ✅ |
| Manual report with photo upload | ✅ |
| Privacy blur (faces & license plates) | ✅ |
| Docker + PostGIS support | ✅ |

## Hardware Notes

- **Laptop**: webcam or video file – works with CPU
- **GPU**: NVIDIA GPU strongly recommended for real-time inference
- **Jetson Nano**: export to ONNX/TensorRT via `detector/export_onnx.py`
- **Android**: export to TFLite for mobile deployment

## License

MIT — Hackathon Prototype
