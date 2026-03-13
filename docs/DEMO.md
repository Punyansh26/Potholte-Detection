# Demo Script (2–4 minutes)

## Prerequisites
- Python 3.10+ with dependencies installed
- Backend running: `python -m uvicorn backend.main:app --reload --port 8000`
- Dashboard open: http://localhost:8000

---

## Step 1: Empty Dashboard (15s)
> "This is PotholeGuard — our autonomous pothole detection and reporting system."

- Show the Leaflet map dashboard — it's empty, no potholes yet
- Point out the stat bar: 0 Total, 0 Critical, 0 Pending, 0 Repaired

## Step 2: Run Edge Detector (45s)
> "Now I'll run our edge detection client on a sample video."

```bash
python detector/edge_client.py --source test_data/sample_video.mp4 --conf 0.3
```

- Show terminal output: detections appearing with pothole IDs, severity, risk scores
- Switch to dashboard: markers appearing on the map in real-time
- Click a marker to show detail panel: severity, confidence, snapshots

## Step 3: Deduplication (30s)
> "Watch — the same pothole from a different angle merges into one record."

- Run a second pass or upload from a different angle
- Show that the detection count increments but no new marker appears
- "Our Haversine-based spatial dedup merges reports within 2.5 meters"

## Step 4: Auto-Filing (30s)
> "When a pothole exceeds our risk threshold of 80, we auto-file to CPGRAMS."

- Show a critical detection triggering the grievance module
- Terminal shows: "⚠️ GRIEVANCE FILED: CPGRAMS-XXXXXXX"
- Click pothole detail: grievance section shows ticket ID and status

## Step 5: Verification (45s)
> "Let's simulate a repair check."

- Click "Verify" on a pothole
- Upload a clean road image → system marks it **Repaired** ✅
- Show marker changes color to cyan
- Upload a still-damaged image when status is Closed → show **Auto-Escalation** ⚠️

## Step 6: Manual Report (15s)
> "Citizens can also report directly via the dashboard."

- Click "Report Pothole", drag photo, click map to pin location, submit
- New marker appears on map

## Step 7: Wrap Up (15s)
> "Our repo includes full test coverage, privacy pipeline with face/plate blur,
>  and documentation for training, deployment, and API usage."

- Show test results: `pytest tests/ -v`
- Mention Docker support, ONNX export, Jetson compatibility
