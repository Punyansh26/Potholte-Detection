# PotholeGuard — Autonomous Pothole Detection & Closed-Loop Reporting

An end-to-end system that **detects potholes** from camera/video feeds using YOLOv8, **stores raw camera and phone sensor events**, **classifies them with a multi-signal sensor-fusion model**, **clusters confirmed potholes into batched complaints**, and **verifies repairs** through ORB/SSIM image comparison — all surfaced on a real-time Leaflet dashboard with an automated CPGRAMS grievance pipeline.

---

## Table of Contents

1. [Architecture](#architecture)
2. [Quick Start](#quick-start)
3. [Environment Variables](#environment-variables)
4. [Running the Edge Detector](#running-the-edge-detector)
5. [Using a Phone Camera](#using-a-phone-camera)
6. [Docker Setup](#docker-setup)
7. [API Reference](#api-reference)
8. [Data Pipeline and Batch Flow](#data-pipeline-and-batch-flow)
9. [Sensor Fusion Model](#sensor-fusion-model)
10. [Risk Scoring and Severity](#risk-scoring-and-severity)
11. [Spatial Deduplication](#spatial-deduplication)
12. [Complaint Filing and Suppression](#complaint-filing-and-suppression)
13. [Repair Verification](#repair-verification)
14. [Privacy and PII Blurring](#privacy-and-pii-blurring)
15. [Demo Ultrasonic Synthesis](#demo-ultrasonic-synthesis)
16. [Database Schema](#database-schema)
17. [Frontend Dashboard](#frontend-dashboard)
18. [Project Structure](#project-structure)
19. [Tests](#tests)
20. [Hardware Notes](#hardware-notes)
21. [Feature Matrix](#feature-matrix)

---

## Architecture

```
+------------------+   POST /detections     +--------------------------------------+
|   Edge Client    | --------------------> |          FastAPI Backend             |
|   (YOLOv8 +      |                        |                                      |
|  Phone Sensors)  |   GET /stream/video    |  1. Raw SensorEvent store (level-0)  |
+------------------+ <------------------- |  2. Sensor-fusion classifier          |
                                            |  3. Haversine spatial dedup (2.5 m)  |
+------------------+   POST /manual_report  |  4. DefectRegistry promotion         |
|  Browser / Phone | --------------------> |  5. Risk scoring (0-100)             |
|  Dashboard SPA   |   GET /potholes        |  6. 24h clustered complaint batch    |
|  (Leaflet map)   | <------------------- |  7. 14-day suppression window        |
+------------------+                        |  8. ORB/SSIM repair verification     |
                                            |  9. Auto-escalation on re-damage     |
                                            +----------------+---------------------+
                                                             |
                              +------------------------------+------------------+
                              |  SQLite / Neon Postgres      |  Mock CPGRAMS    |
                              |  + PostGIS (Docker)          |  Grievance Portal|
                              +------------------------------+------------------+
```

---

## Quick Start

### 1. Create and activate environment

```bash
conda create -n potholepy python=3.11 -y
conda activate potholepy
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment

```bash
# Windows
copy .env.example .env

# Linux / macOS
cp .env.example .env
```

Open `.env` and set at minimum:

```env
DATABASE_URL=sqlite:///./pothole.db        # or your Neon/Postgres URL
RESEND_API_KEY=re_your_key_here            # leave blank for local email preview
COMPLAINT_NOTIFY_CC=you@example.com
```

### 4. Start the backend

```bash
conda activate potholepy
python -m uvicorn backend.main:app --reload --port 8003
```

The server starts at **http://localhost:8003**.
API docs (Swagger UI) are available at **http://localhost:8003/docs**.

### 5. Open the dashboard

Navigate to **http://localhost:8003** in any browser. The dashboard auto-refreshes every 5 seconds.

### 6. Run the edge detector (optional)

```bash
# Webcam with live preview window
python detector/edge_client.py --source 0 --api http://localhost:8003 --preview

# Video file
python detector/edge_client.py --source dashcam.mp4 --api http://localhost:8003

# Phone IP camera
python detector/edge_client.py --source http://192.168.1.10:8080/video --api http://localhost:8003 --preview --phone-gps
```

---

## Environment Variables

All variables can be set in a `.env` file in the project root. The application uses `pydantic-settings` for validation and type coercion.

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./pothole.db` | SQLAlchemy connection string. Use `postgresql://user:pass@host/db` for production. |
| `STORAGE_PATH` | `./storage/snapshots` | Directory where snapshot JPEGs are saved. |
| `CPGRAMS_ENDPOINT` | `http://localhost:8003/mock/cpgrams/grievance` | Where batch complaints are POSTed. Change to real portal URL in production. |
| `RISK_THRESHOLD` | `80` | Potholes scoring >= this auto-file a CPGRAMS complaint on detection. |
| `RESEND_API_KEY` | *(empty)* | Resend API key for outbound complaint emails. If blank, emails are saved as HTML previews in `storage/emails/`. |
| `RESEND_FROM_EMAIL` | `PotholeGuard <onboarding@resend.dev>` | Sender address shown in complaint emails. |
| `COMPLAINT_NOTIFY_CC` | `rtxxxzz69@gmail.com` | Comma-separated emails CC'd on every complaint notification. |
| `AUTHORITY_DEFAULT_EMAIL` | `roads@civic-authority.demo` | Default complaint recipient. |
| `AUTHORITY_RAIPUR_EMAIL` | `raipur.roadcell@civic-authority.demo` | Complaint recipient when coordinates fall in the Raipur region. |
| `YOLO_MODEL` | `keremberke/yolov8n-pothole-segmentation` | HuggingFace Hub model ID or local `.pt` path. |
| `YOLO_CONF` | `0.25` | Detection confidence threshold (0-1). |
| `YOLO_IOU` | `0.45` | NMS IoU threshold. |
| `YOLO_MAX_DET` | `1000` | Max detections per frame. |
| `DEDUP_RADIUS_METERS` | `2.5` | Potholes within this radius of each other are merged into one record. |
| `COMPLAINT_INTERVAL_HOURS` | `24` | Lookback window for the batch complaint job. |
| `COMPLAINT_CLUSTER_RADIUS_METERS` | `25.0` | Radius for grouping nearby potholes into a single cluster complaint. |
| `COMPLAINT_SUPPRESSION_RADIUS_METERS` | `35.0` | No new complaint is filed for an area with an active complaint within this radius. |
| `COMPLAINT_EXPIRY_DAYS` | `14` | After this many days an expired complaint allows fresh filing for the same area. |
| `COMPLAINT_BATCH_EMAIL_ALWAYS` | `True` | Send the batch-summary email even when no new complaints were filed. |
| `DEFAULT_LAT` / `DEFAULT_LON` | `19.076` / `72.8777` | Fallback coordinates (Mumbai) used when GPS is unavailable. |
| `CAMERA_ID` | `edge-001` | Default camera identifier tag on events. |

> **Test mode:** When `pytest` is detected at runtime, `DATABASE_URL` is automatically switched to `TEST_DATABASE_URL` (or `sqlite:///./test_pothole.db`) so tests never touch the production database.

---

## Running the Edge Detector

The edge client (`detector/edge_client.py`) runs YOLOv8 locally and streams detections to the backend. Works with webcams, video files, image directories, and live phone camera streams.

### CLI flags

| Flag | Default | Description |
|---|---|---|
| `--source` | `0` | Camera index, video file path, image directory, or HTTP/RTSP URL |
| `--api` | `http://localhost:8003` | Backend API base URL |
| `--model` | `keremberke/yolov8n-pothole-segmentation` | YOLO model HF ID or local `.pt` path |
| `--conf` | `0.25` | Confidence threshold |
| `--camera-id` | `edge-001` | Tag attached to every event |
| `--lat` / `--lon` | Config defaults | Fixed GPS coordinates (use when no phone GPS) |
| `--gps-track` | *(none)* | Path to a JSON GPS track `[{lat, lon, timestamp}, ...]` for scripted replay |
| `--preview` | off | Open an OpenCV window with live bounding boxes, severity labels, GPS overlay, and grievance alerts |
| `--phone-gps` | off | Pull live GPS from the phone IP Webcam host (`/gps.json`, `/sensors.json`, `/status.json`) |
| `--skip` | `1` | Run YOLO every N-th frame (useful for high-FPS sources) |
| `--max-frames` | unlimited | Stop after this many frames |

### Examples

```bash
# Default webcam with live preview
python detector/edge_client.py --source 0 --preview

# Dashcam video file, post to remote server
python detector/edge_client.py --source dashcam.mp4 --api http://10.0.0.5:8003

# Android phone camera (IP Webcam app)
python detector/edge_client.py \
  --source http://192.168.1.10:8080/video \
  --api http://localhost:8003 \
  --preview \
  --phone-gps

# Phone camera with GPS track replay
python detector/edge_client.py \
  --source http://192.168.1.10:8080/video \
  --gps-track test_data/sample_gps_track.json \
  --preview

# Image directory batch scan
python detector/edge_client.py --source ./test_images/ --max-frames 500

# Use a local fine-tuned model
python detector/edge_client.py --source 0 --model models/pothole.pt --conf 0.35
```

### Preview window legend

When `--preview` is active, the OpenCV window shows:

- **Green box** — low severity
- **Yellow box** — medium severity
- **Orange box** — high severity
- **Red box** — critical severity
- Each box is labelled with: `severity | conf% | ID:<pothole_id> | risk:<score>`
- GPS coordinates and device ID overlaid in the top-left
- Flashing red `GRIEVANCE FILED` banner when a high-risk detection triggers an instant complaint

---

## Using a Phone Camera

### Browser camera (Live Cam tab)

Open the dashboard on your phone at `http://<laptop-ip>:8003` and tap the **Live Cam** tab. The browser streams the phone camera in-page, samples frames, and sends them to the backend for detection.

> Mobile browsers require HTTPS or `localhost` to grant camera permissions. If your phone blocks camera access over LAN HTTP, expose the app through a reverse proxy with HTTPS, or use IP Webcam mode below.

### IP Webcam mode (Android)

1. Install **IP Webcam** from the Play Store and tap **Start server**. Note the IP and port (e.g. `192.168.1.10:8080`).
2. Verify connectivity from your laptop: open `http://192.168.1.10:8080` in a browser.
3. Run the edge client:

```bash
python detector/edge_client.py \
  --source http://192.168.1.10:8080/video \
  --api http://localhost:8003 \
  --preview \
  --phone-gps
```

4. If the MJPEG stream drops, the client automatically falls back to snapshot polling via `http://192.168.1.10:8080/shot.jpg`.
5. Keep both devices on the same Wi-Fi. Disable VPN or mobile-data switching on the phone if the IP changes.
6. Alternatively, point the dashboard **Live Cam** tab at the IP Webcam URL to stream MJPEG directly with YOLO applied server-side.

### Fetching phone GPS automatically

Pass `--phone-gps` to extract GPS from the phone. The client probes these endpoints in order:

- `/gps.json`
- `/sensors.json`
- `/status.json`

If live GPS is found, it is attached to every detection event, replacing the fallback `--lat/--lon` values.

---

## Docker Setup

Docker Compose starts a PostGIS-enabled PostgreSQL database alongside the backend container.

```bash
# Start both services (first run builds the image)
POSTGRES_PASSWORD=secret docker-compose up --build

# Run in the background
POSTGRES_PASSWORD=secret docker-compose up -d --build

# Stop and remove containers
docker-compose down

# Stop and remove containers + volumes (clears all data)
docker-compose down -v
```

The backend is available at **http://localhost:8000** when using Docker (port 8000, not 8003).

### Services

| Service | Image | Port | Description |
|---|---|---|---|
| `db` | `postgis/postgis:15-3.4` | `5432` | PostGIS PostgreSQL. Health-checked with `pg_isready`. |
| `backend` | Built from `Dockerfile` | `8000` | FastAPI app. Waits for `db` to be healthy before starting. Snapshots are persisted on a named volume. |

---

## API Reference

Interactive docs (Swagger UI) at **http://localhost:8003/docs**.

### Health

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Returns `{"status": "ok"}`. Use for load-balancer health checks. |

---

### Detections

#### `POST /detections`

Ingest a single pothole detection event from an edge device. Runs the full pipeline: sensor-fusion classification -> spatial dedup -> DefectRegistry promotion -> optional auto-complaint.

**Request body:**
```json
{
  "camera_id": "edge-001",
  "device_id": "jetson-nano-01",
  "timestamp": "2026-03-15T10:30:00Z",
  "lat": 19.0760,
  "lon": 72.8777,
  "vision_triggered": true,
  "bbox": [120, 200, 380, 420],
  "confidence": 0.87,
  "severity_est": "high",
  "snapshot_base64": "<base64 JPEG>",
  "accel_x": 0.12, "accel_y": -0.05, "accel_z": 9.95,
  "gyro_x": 1.2, "gyro_y": -0.3, "gyro_z_dps": 0.8,
  "gps_accuracy_m": 4.5,
  "ultrasonic_distance_cm": 18.3,
  "estimated_depth_cm": 5.7,
  "sensor_fusion_score": 0.83,
  "sensor_source": "demo-ultrasonic",
  "sensor_samples_cm": [18.1, 18.3, 18.5, 18.2, 18.4, 18.3],
  "vibration_rms_g": 0.45,
  "peak_accel_g": 1.23,
  "shock_index": 62,
  "roughness_index": 55.0,
  "speed_kph": 28.5,
  "pitch_deg": -2.1, "roll_deg": 0.4, "yaw_deg": 187.3
}
```

**Response:**
```json
{
  "pothole_id": 42,
  "is_new": true,
  "severity": "high",
  "risk_score": 84.2,
  "accepted": true,
  "raw_event_id": 117,
  "sensor_model_label": "confirmed",
  "sensor_model_score": 0.83,
  "grievance_filed": true,
  "grievance_id": "CPGRAMS-A3F9B21C"
}
```

#### `POST /live/detect`

Submit a single browser frame for real-time detection, used by the Live Cam tab.

```json
{
  "image_base64": "<base64 JPEG>",
  "camera_id": "browser-live",
  "lat": 19.076,
  "lon": 72.877,
  "persist": true
}
```

Returns a list of detections (one per pothole found), plus frame dimensions and timestamp.

#### `GET /sensor-events`

List raw level-0 sensor events. Query params: `stage`, `label`, `camera_id`, `limit` (1-250, default 50).

#### `GET /potholes`

List all pothole records. Query params: `severity`, `repaired` (bool), `min_lat`, `max_lat`, `min_lon`, `max_lon`.

#### `GET /potholes/{pothole_id}`

Full pothole record including all linked grievance history.

---

### Complaints

#### `POST /complaints/process`

Trigger the batch complaint filing job manually.

```json
{ "as_of": "2026-03-15T12:00:00Z" }
```

**Response:**
```json
{
  "processed_at": "2026-03-15T12:00:00Z",
  "window_started_at": "2026-03-14T12:00:00Z",
  "clusters_considered": 5,
  "complaints_registered": 3,
  "complaints_suppressed": 2,
  "complaints_failed": 0,
  "batch_email_sent": true,
  "batch_email_message_id": "msg_abc123",
  "grievances": []
}
```

#### `GET /complaints`

List all grievance records ordered by submission date descending.

---

### Manual Report

#### `POST /manual_report`

Submit a citizen pothole report from the map.

```json
{
  "lat": 19.0760,
  "lon": 72.8777,
  "description": "Large pothole near the bus stop",
  "severity": "high",
  "snapshot_base64": "<base64 JPEG>"
}
```

---

### Verification

#### `PUT /potholes/{pothole_id}/verify`

Compare a new snapshot against the stored image to determine if the pothole has been repaired.

```json
{ "snapshot_base64": "<base64 JPEG of repaired site>" }
```

**Response:**
```json
{
  "pothole_id": 42,
  "previous_status": "Registered",
  "new_status": "Resolved",
  "similarity_score": 0.21,
  "action_taken": "marked_repaired"
}
```

`action_taken` values: `marked_repaired`, `still_damaged`, `auto_escalated`, `no_previous_image`, `comparison_failed`.

---

### Streaming

#### `GET /stream/video`

Server-sent MJPEG stream with YOLO bounding boxes drawn on every frame. Used by the Live Cam tab `<img>` element.

| Param | Default | Description |
|---|---|---|
| `source` | `0` | Camera index, video URL, or IP Webcam URL |
| `conf` | `0.25` | Detection confidence threshold |
| `skip` | `2` | Run YOLO every N frames |
| `max_dim` | `640` | Resize input before inference |
| `post` | `true` | POST detections to `/detections` |
| `camera_id` | `live-stream` | Camera tag |
| `lat`, `lon` | Config defaults | GPS coordinates |
| `gps_accuracy_m` | — | GPS accuracy hint |

#### `GET /stream/telemetry`

Latest simulated vehicle telemetry snapshot as JSON. Polled every 1.5 s by the dashboard.

---

### Telemetry

#### `POST /telemetry/ingest`

Ingest raw phone sensor data (accelerometer, gyro, GPS). The sensor classifier determines whether the event represents a pothole and promotes it if so.

#### `GET /telemetry/latest`

Returns the last telemetry payload processed by `/telemetry/ingest`.

#### `GET /telemetry/ipwebcam?source=<url>`

Fetch and classify sensor data live from an IP Webcam host.

---

### Mock CPGRAMS Portal

Simulates the Indian government CPGRAMS grievance portal.

| Method | Path | Description |
|---|---|---|
| `POST` | `/mock/cpgrams/grievance` | File a new complaint. Returns `ticket_id` (`CPGRAMS-<8hex>`). |
| `GET` | `/mock/cpgrams/status/{ticket_id}` | Get status of a specific ticket. |
| `PUT` | `/mock/cpgrams/status/{ticket_id}?status=Resolved` | Manually update a ticket status. |
| `GET` | `/mock/cpgrams/tickets` | List all in-memory tickets. |

---

### Static Routes

| Path | Description |
|---|---|
| `GET /snapshots/{filename}` | Serves saved snapshot JPEGs from `./storage/snapshots/` |
| `GET /` | Serves the `frontend/` single-page application (SPA catch-all) |

---

## Data Pipeline and Batch Flow

Every detection goes through a strict multi-stage pipeline before becoming a complaint:

```
Camera Frame
     |
     v
YOLOv8 Inference  -- bbox, confidence, severity_est
     |
     v
Demo Ultrasonic Profile -- ultrasonic_distance_cm, estimated_depth_cm, fusion_score
     |
     v
POST /detections
     |
     v
[1] SensorEvent saved (level-0 raw) -- ALWAYS, regardless of outcome
     |
     v
[2] Sensor Fusion Classifier
     |-- score >= 0.48 --> label: "confirmed"
     +-- score < 0.48  --> label: "rejected" -- pipeline stops here
     |
     v
[3] Severity Fusion (visual bbox area + ultrasonic depth --> max severity)
     |
     v
[4] Risk Score (0-100) computed
     |
     v
[5] Spatial Dedup (Haversine 2.5 m radius)
     |-- nearby pothole found --> merge (increment count, upgrade severity, update snapshots)
     +-- no nearby pothole   --> create new DefectRegistry record
     |
     v
[6] Auto-complaint check (risk_score >= RISK_THRESHOLD)
     +-- yes --> POST to CPGRAMS immediately, save GrievanceLifecycle
     |
     v
[7] Batch job (POST /complaints/process)
     |-- load unrepaired potholes in last 24 h
     |-- greedy spatial cluster (25 m radius)
     |-- suppression check (35 m, 14-day window)
     |-- POST cluster complaint to CPGRAMS
     |-- save GrievanceLifecycle records
     +-- send notification + batch summary email via Resend
```

---

## Sensor Fusion Model

**Model name:** `demo-phone-sensor-fusion-v1`
**Decision threshold:** `0.48`

The classifier combines vision and physical sensor signals into a single probability score:

| Signal | Weight | Description |
|---|---|---|
| `vision_confidence` | 0.62 | YOLO detection confidence |
| `shock_g` | 0.14 | Normalised IMU shock: `(|accel| - 9.81) / 9.81` |
| `roughness_index` | 0.10 | Road roughness from accelerometer data |
| `depth_signal` | 0.10 | Derived from `ultrasonic_distance_cm` or `estimated_depth_cm` |
| `speed_kph` (normalised) | 0.04 | Vehicle speed context |

A score >= 0.48 labels the event `confirmed` and promotes it to the DefectRegistry. Scores below threshold label it `rejected` — the raw SensorEvent is still saved for audit, but no pothole record is created or updated.

---

## Risk Scoring and Severity

### Severity levels

Severity is first estimated from the YOLOv8 bounding box area relative to the frame, then fused with the ultrasonic depth reading (whichever gives a higher severity wins).

| Level | BBox area ratio | Ultrasonic depth |
|---|---|---|
| `low` | < 3% | < 5 cm |
| `medium` | 3-8% | 5-9 cm |
| `high` | 8-15% | 9-14 cm |
| `critical` | > 15% | >= 14 cm |

### Risk score formula

```
risk_score = (severity_weight x 40) + (confidence x 20) + (exposure_factor x 40)
           + depth_bonus (up to +8)
           + fusion_score_bonus (up to +4)
```

Clipped to 0-100. Potholes scoring >= `RISK_THRESHOLD` (default 80) trigger an immediate auto-complaint without waiting for the batch job.

---

## Spatial Deduplication

The dedup service (`backend/services/dedup.py`) prevents duplicate pothole records for the same physical location:

1. A bounding-box pre-filter narrows candidates to a small geographic window.
2. Exact Haversine distance is computed for each candidate.
3. The closest unrepaired pothole within `DEDUP_RADIUS_METERS` (default **2.5 m**) is returned.
4. If found: the existing record is **merged** — detection count incremented, severity upgraded (never downgraded), confidence averaged, new snapshot appended, IMU fields updated.
5. If not found: a new `DefectRegistry` row is created.

---

## Complaint Filing and Suppression

The batch complaint job implements a full lifecycle:

1. **Clustering:** Nearby confirmed potholes from the last 24 hours are grouped using greedy single-linkage clustering (25 m radius). One complaint is filed per cluster.
2. **Suppression check:** Before filing, the system looks for any active, unexpired GrievanceLifecycle within 35 m. If one exists, the new complaint is suppressed and the reason is logged.
3. **Filing:** A CPGRAMS-format payload is built (title, description, coordinates, risk score, snapshot attachments) and POSTed to `CPGRAMS_ENDPOINT`.
4. **Email notification:** A formatted HTML complaint email is sent to the routed authority email (Raipur-region or default), with CC to `COMPLAINT_NOTIFY_CC`.
5. **Expiry:** After `COMPLAINT_EXPIRY_DAYS` (default 14) days a complaint moves to `Expired` status and the suppression window lifts — the same area can now raise a fresh complaint.
6. **Auto-escalation:** If `PUT /potholes/{id}/verify` determines the pothole is still damaged despite the portal status being "Closed/Resolved", all linked grievances are re-opened as `Appealed`.

---

## Repair Verification

The verification service (`backend/services/verification.py`) uses computer vision to confirm whether a repair has actually been completed:

1. Both the new and stored snapshots are decoded and resized to **256 x 256** greyscale.
2. **SSIM (Structural Similarity Index)** measures overall surface similarity.
3. **ORB feature matching** extracts 500 keypoints from each image and matches them with a Hamming-distance BFMatcher (threshold < 50 px).
4. SSIM < **0.35** -> surface substantially changed -> `marked_repaired`.
5. SSIM >= 0.35 but portal reported "Closed/Resolved" -> `auto_escalated` (grievance re-opened as "Appealed").
6. No previous snapshot -> `no_previous_image`.

---

## Privacy and PII Blurring

The privacy module (`privacy/blur.py`) automatically blurs faces and license plates in snapshots before they are stored or transmitted.

- **Face detection:** OpenCV `haarcascade_frontalface_default.xml` — detectMultiScale (scale 1.1, 5 neighbours, min 30x30 px)
- **Plate detection:** OpenCV `haarcascade_russian_plate_number.xml` — detectMultiScale (scale 1.1, 4 neighbours, min 60x20 px)
- **Blur:** 51x51 Gaussian kernel (sigma=30) applied to each detected region
- Gracefully skips a cascade type if the XML file is missing, logging a warning instead of crashing

**CLI usage:**
```bash
python privacy/blur.py input.jpg output_blurred.jpg
```

> **Integration note:** The blur module is implemented and tested. To activate it in the ingestion pipeline, call `blur_pii(img)` from `save_snapshot()` in `backend/services/detection_ingest.py` before writing to disk.

---

## Demo Ultrasonic Synthesis

When no physical ultrasonic sensor hardware is present, `detector/demo_ultrasonic.py` generates **realistic deterministic synthetic sensor readings** so the full sensor-fusion pipeline can run during demos.

**Algorithm:**
```
base_depth_cm = severity_map[severity]  # low=2.5, medium=5.5, high=9.0, critical=13.0
depth_cm      = base_depth + (bbox_area_ratio x 26) + (confidence x 2.4) x center_bias
distance_cm   = 24.0 - depth_cm         # vehicle-mounted downward-facing sensor, 24 cm baseline

fusion_score  = 0.62 + (confidence x 0.2) + ((depth / 20) x 0.18)  -- capped at 0.99
```

Six sample readings are generated with +-0.55 cm jitter using a seeded RNG (seed derived from bbox coordinates) so the same detection always reproduces identical readings.

**Output fields:**

| Field | Description |
|---|---|
| `ultrasonic_distance_cm` | Ground clearance reading |
| `estimated_depth_cm` | Estimated pothole depth |
| `sensor_fusion_score` | Composite confidence (0-1) |
| `sensor_source` | `"demo-ultrasonic"` |
| `sensor_samples_cm` | List of 6 raw sample readings |

---

## Database Schema

### `DefectRegistry` — spatial pothole registry

| Column | Type | Description |
|---|---|---|
| `pothole_id` | PK Integer | Auto-increment |
| `lat`, `lon` | Float | WGS-84 centroid coordinates |
| `first_seen`, `last_seen` | DateTime (tz) | Detection timestamps |
| `severity` | String | `low` / `medium` / `high` / `critical` |
| `risk_score` | Float | 0-100 composite score |
| `is_repaired` | Boolean | Default `False` |
| `avg_confidence` | Float | Running average YOLO confidence |
| `detection_count` | Integer | Number of raw events merged |
| `snapshots` | JSON | List of snapshot URL strings |
| `description` | Text | Human-readable notes |
| `latest_ultrasonic_distance_cm` | Float | Most recent ground clearance |
| `estimated_depth_cm` | Float | Pothole depth in cm |
| `sensor_fusion_score` | Float | Composite 0-1 score |
| `sensor_source` | String | e.g. `demo-ultrasonic`, `demo-vehicle-imu` |
| `sensor_samples_cm` | JSON | Raw ultrasonic sample array |
| `latest_vibration_rms_g` | Float | RMS vibration magnitude |
| `latest_peak_accel_g` | Float | Peak accelerometer reading |
| `latest_shock_index` | Integer | 0-100 shock severity |
| `latest_roughness_index` | Float | 0-100 road roughness |
| `latest_speed_kph` | Float | Vehicle speed at detection |
| `latest_pitch_deg`, `latest_roll_deg`, `latest_yaw_deg` | Float | Vehicle orientation |

### `SensorEvent` — raw level-0 event log

| Column | Type | Description |
|---|---|---|
| `id` | PK Integer | |
| `camera_id`, `device_id` | String | Source identifiers |
| `recorded_at` | DateTime (tz) | |
| `lat`, `lon` | Float | |
| `vision_triggered` | Boolean | Was vision the trigger? |
| `vision_confidence` | Float | YOLO confidence |
| `bbox` | JSON | Bounding box [x1, y1, x2, y2] |
| `snapshot_url` | String | Saved snapshot path |
| `sensor_payload` | JSON | Full raw payload |
| `feature_vector` | JSON | Features extracted by classifier |
| `classifier_label` | String | `confirmed` / `rejected` / `pending` |
| `classifier_score` | Float | Sensor model score |
| `ingestion_stage` | String | `raw` / `confirmed` / `rejected` |
| `pothole_id` | FK | Linked `DefectRegistry` ID (set if promoted) |

### `GrievanceLifecycle` — complaint records

| Column | Type | Description |
|---|---|---|
| `id` | PK Integer | |
| `pothole_id` | FK | Linked pothole |
| `grievance_system` | String | Default `CPGRAMS` |
| `grievance_id` | String | Portal ticket ID |
| `status` | String | `Pending` / `Registered` / `Under Review` / `Resolved` / `Appealed` / `Expired` |
| `submitted_at` | DateTime (tz) | |
| `sla_deadline` | DateTime (tz) | Expected resolution date |
| `payload` | JSON | Full payload sent to CPGRAMS |
| `cluster_lat`, `cluster_lon` | Float | Cluster centroid |
| `cluster_radius_m` | Float | Cluster radius |
| `evidence_count` | Integer | Number of raw confirmations in cluster |
| `complaint_expires_at` | DateTime (tz) | Suppression window end |
| `suppression_reason` | Text | Why this complaint was suppressed |

> **Schema migration:** `_ensure_hackathon_columns()` runs at startup and adds any missing columns via `ALTER TABLE ... ADD COLUMN`. No Alembic migrations are required for incremental updates.

---

## Frontend Dashboard

The dashboard (`frontend/`) is a single-page application served directly by FastAPI.

### Map tab

The main operations view:

- **Leaflet map** centered on Mumbai (CartoDB Dark Matter tiles). Markers are color-coded by severity. Critical unrepaired potholes show an animated pulse ring.
- **Hackathon Control Room panel:** one-click `Run Complaint Batch` button, live counts for Raw Events / Confirmed / Rejected / Filed Complaints, and batch run summary.
- **Priority Hotspots panel:** top 6 unrepaired potholes ranked by `detection_count x risk_score`.
- **Raw Sensor Events panel:** last 10 level-0 events with stage badge, camera ID, and sensor payload preview.
- **Filed Complaints panel:** latest complaint card and a ledger of the last 8 grievances.
- **Filter bar:** All / Critical / High / Medium / Low / Repaired.

### Live Cam tab

Real-time camera view:

- Enter an IP Webcam URL and click **Connect** (or leave blank for server default camera).
- Confidence and frame-skip sliders control detection sensitivity and performance.
- MJPEG stream rendered via `GET /stream/video` with YOLO annotations drawn server-side.
- GPS status indicator via `navigator.geolocation`.
- Live detection list (last 20 events) and total pothole count badge.
- **Sensor telemetry panel** with 14 live fields refreshed every 1.5 seconds: vibration RMS, peak accel, shock index, roughness index, ground clearance, estimated depth, fusion score, severity, speed, heading, pitch, roll, yaw, advisory text.

### Pothole detail modal

Click any map marker to open a full detail panel:

- All pothole fields (ID, coordinates, severity, risk score, detection count, timestamps)
- Snapshot gallery (thumbnails of all saved images)
- Full grievance history table
- **Verify** button — upload a new photo to check repair status
- **Report Grievance** button — re-file or escalate a complaint

### Report Pothole modal

Click the **Report Pothole** button, then click the map to pin a location. Fill in severity and optional photo, then submit to `POST /manual_report`.

### Auto-refresh

All dashboard data refreshes automatically every **5 seconds** by polling `/potholes`, `/sensor-events`, and `/complaints` in parallel.

---

## Project Structure

```
+-- backend/
|   +-- main.py                  # FastAPI app, router registration, DB init
|   +-- database.py              # SQLAlchemy ORM models & DB setup
|   +-- models.py                # Pydantic request/response schemas
|   +-- routers/
|   |   +-- detections.py        # POST /detections, POST /live/detect, GET /potholes
|   |   +-- complaints.py        # POST /complaints/process, GET /complaints
|   |   +-- manual_report.py     # POST /manual_report
|   |   +-- stream.py            # GET /stream/video, GET /stream/telemetry
|   |   +-- telemetry.py         # POST /telemetry/ingest, GET /telemetry/*
|   |   +-- verification.py      # PUT /potholes/{id}/verify
|   |   +-- mock_cpgrams.py      # Simulated CPGRAMS portal
|   +-- services/
|       +-- dedup.py             # Haversine spatial dedup (2.5 m)
|       +-- detection_ingest.py  # Main ingestion pipeline
|       +-- risk_scoring.py      # Severity fusion + risk score formula
|       +-- sensor_classifier.py # Sensor fusion model (weighted linear)
|       +-- grievance.py         # Cluster, suppress, file, email
|       +-- live_detection.py    # Singleton YOLO detector cache
|       +-- verification.py      # ORB + SSIM repair comparison
+-- detector/
|   +-- inference.py             # PotholeDetector class (YOLOv8)
|   +-- edge_client.py           # Edge device -> backend streaming client
|   +-- demo_ultrasonic.py       # Synthetic ultrasonic sensor profile
|   +-- train.py                 # YOLOv8 fine-tuning script
|   +-- export_onnx.py           # ONNX / TFLite export
|   +-- download_model.py        # Pre-download model weights
+-- frontend/
|   +-- index.html               # Dashboard SPA
|   +-- index.css                # Dark glassmorphism design system
|   +-- app.js                   # Leaflet map + dashboard logic
|   +-- camera.js                # Live Cam tab logic
+-- privacy/
|   +-- blur.py                  # Haar cascade face & plate blur
+-- tests/
|   +-- test_api.py              # Core ingestion + live detect tests
|   +-- test_complaints.py       # Batch flow & suppression tests
|   +-- test_dedup.py            # Spatial dedup unit tests
|   +-- test_edge_client.py      # Edge client URL candidate tests
|   +-- test_grievance.py        # Severity, risk score, CPGRAMS payload tests
|   +-- test_verification.py     # ORB/SSIM comparison tests
+-- docs/
|   +-- API.md                   # Extended API documentation
|   +-- MODEL.md                 # Model training & evaluation details
|   +-- PRIVACY.md               # Privacy compliance notes
|   +-- DEMO.md                  # Demo walkthrough script
|   +-- TESTS.md                 # Test suite documentation
+-- scripts/
|   +-- seed_raipur_demo.py      # Seed database with Raipur demo data
|   +-- basic_send.py            # Minimal detection POST example
+-- test_data/
|   +-- sample_gps_track.json    # Example GPS track for --gps-track flag
|   +-- sample_ultrasonic_demo.json
+-- config.py                    # Pydantic settings (all env vars)
+-- docker-compose.yml
+-- Dockerfile
+-- requirements.txt
```

---

## Tests

Run the full test suite:

```bash
conda activate potholepy
pytest tests/ -v
```

Run a specific test file:

```bash
pytest tests/test_api.py -v
pytest tests/test_dedup.py -v
pytest tests/test_complaints.py -v
pytest tests/test_grievance.py -v
pytest tests/test_verification.py -v
pytest tests/test_edge_client.py -v
```

Run with coverage report:

```bash
pytest tests/ --cov=backend --cov-report=term-missing
```

### Test suite summary

| File | Coverage |
|---|---|
| `test_api.py` | Health endpoint, detection ingestion, snapshot storage, ultrasonic demo data, IMU telemetry, live detect with stubbed YOLO |
| `test_complaints.py` | Raw event saved before confirmation, low-signal rejection, full 14-day suppression and re-raise cycle |
| `test_dedup.py` | Merge within 2.5 m, separate beyond 2.5 m, detection count increment, Haversine accuracy |
| `test_edge_client.py` | IP Webcam URL candidate list (MJPEG -> snapshot fallback) |
| `test_grievance.py` | Severity thresholds, risk score range and formula, CPGRAMS payload structure |
| `test_verification.py` | Identical images -> not repaired, different images -> repaired, no baseline image, SSIM/ORB return type |

All tests use an in-memory SQLite test database that is fully reset before each test function.

---

## Hardware Notes

| Platform | Notes |
|---|---|
| **Laptop / Desktop** | Works on CPU. Use webcam or video file. No GPU needed for testing. |
| **NVIDIA GPU** | Strongly recommended for real-time inference at >= 15 FPS. CUDA detected automatically by `ultralytics`. |
| **Jetson Nano / Orin** | Export to ONNX or TensorRT: `python detector/export_onnx.py --model models/pothole.pt --format onnx` |
| **Android phone** | Use as IP camera via the **IP Webcam** app. Export to TFLite for on-device inference: `python detector/export_onnx.py --format tflite` |
| **Raspberry Pi** | Use the ONNX runtime export for CPU-optimised inference. |

---

## Feature Matrix

| Feature | Status | Notes |
|---|---|---|
| YOLOv8 pothole detection (image / video / webcam) | Yes | `keremberke/yolov8n-pothole-segmentation` |
| Live server-side MJPEG stream with YOLO overlay | Yes | `GET /stream/video` |
| Live browser camera streaming + in-browser overlay | Yes | Live Cam tab |
| IP Webcam Android integration + auto-fallback | Yes | MJPEG -> snapshot polling |
| Raw level-0 sensor event store | Yes | Every trigger saved before classification |
| Sensor-fusion pothole classifier (5-signal) | Yes | `demo-phone-sensor-fusion-v1` |
| Demo ultrasonic depth synthesis | Yes | Deterministic, seeded per detection |
| Haversine spatial deduplication (2.5 m) | Yes | Merge, never duplicate |
| Severity fusion (visual + ultrasonic) | Yes | Takes max of both signals |
| Risk scoring (0-100) | Yes | Multi-factor formula |
| Auto-complaint on risk score >= threshold | Yes | Immediate CPGRAMS filing |
| 24h clustered batch complaint filing | Yes | Greedy 25 m clustering |
| 14-day complaint suppression window | Yes | Configurable via env |
| Complaint expiry + re-raise | Yes | After 14 days |
| Complaint email via Resend API | Yes | Routed by municipality |
| Repair verification (ORB + SSIM) | Yes | 256x256 greyscale comparison |
| Auto-escalation on re-damage after close | Yes | "Appealed" status |
| Manual citizen report with photo | Yes | Click-to-pin on map |
| Real-time Leaflet dashboard (dark theme) | Yes | 5 s auto-refresh |
| Priority hotspot ranking | Yes | `detection_count x risk_score` |
| Phone sensor telemetry ingestion | Yes | `/telemetry/ingest` |
| Privacy blur (faces + license plates) | Yes | `privacy/blur.py` (Haar cascade) |
| Docker + PostGIS support | Yes | `docker-compose.yml` |
| SQLite (dev) + Postgres (prod) | Yes | Switched via `DATABASE_URL` |
| Mock CPGRAMS portal | Yes | In-memory ticket store |
| ONNX / TFLite export | Yes | `detector/export_onnx.py` |
| pytest test suite (6 modules) | Yes | Auto-reset isolated test DB |

---

## License

MIT — Hackathon Prototype
