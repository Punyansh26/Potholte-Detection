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
python -m uvicorn backend.main:app --reload --port 8003
```

### 4. Open the dashboard
Visit **http://localhost:8003** in your browser.

### 5. Run the edge detector
```bash
# Webcam
python detector/edge_client.py --source 0

# Video file
python detector/edge_client.py --source dashcam.mp4

# Phone IP camera stream
python detector/edge_client.py --source http://192.168.1.25:8080/video

# Image directory
python detector/edge_client.py --source ./test_images/
```

### 6. Use a phone camera

- Open the dashboard on the phone itself and tap **Start Camera**. The live panel streams the camera preview in-browser and sends sampled frames to the backend for pothole detection.
- Mobile browsers usually require **HTTPS** (or `localhost`) for camera access. If your phone cannot grant camera permissions over LAN HTTP, expose the app with HTTPS or use the phone as an IP camera source.
- For IP camera mode, run an app such as **IP Webcam**, **DroidCam**, or **Camo**, then pass the stream URL to `detector/edge_client.py --source <url>`.

#### IP Webcam setup

1. Install **IP Webcam** on Android and tap **Start server**.
2. On the laptop, open `http://PHONE_IP:8080` in a browser first. If that page does not load, the issue is network or the server is not running yet.
3. Try the stream URL first:

```bash
python detector/edge_client.py --source http://PHONE_IP:8080/video
```

4. If OpenCV cannot keep the MJPEG stream open, the client now falls back automatically to snapshot polling through `http://PHONE_IP:8080/shot.jpg`.
5. Keep phone and laptop on the same Wi-Fi, and disable mobile-data switching/VPN on the phone if the IP changes or stops responding.

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
| Live browser camera streaming + overlay detection | ✅ |
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
