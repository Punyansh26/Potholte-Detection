"""Edge detection client — runs inference and POSTs detections to the backend.

Usage examples:
  # Webcam
  python detector/edge_client.py --source 0

  # Video file
  python detector/edge_client.py --source dashcam.mp4

    # Phone IP camera stream (e.g. IP Webcam / DroidCam HTTP or RTSP URL)
    python detector/edge_client.py --source http://192.168.1.25:8080/video

  # Image directory
  python detector/edge_client.py --source ./test_images/

  # With simulated GPS track
  python detector/edge_client.py --source dashcam.mp4 --gps-track track.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import glob
from urllib.parse import urlparse
import httpx
import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from detector.inference import PotholeDetector
from config import settings


def load_gps_track(path: str) -> list[dict]:
    """Load a JSON GPS track: [{"lat": ..., "lon": ..., "timestamp": ...}, ...]"""
    if not path or not os.path.exists(path):
        return []
    with open(path) as f:
        return json.load(f)


def post_detection(det: dict, api_url: str) -> dict | None:
    """POST a single detection to the backend."""
    try:
        resp = httpx.post(f"{api_url}/detections", json=det, timeout=10)
        resp.raise_for_status()
        result = resp.json()
        print(f"  → Pothole #{result['pothole_id']}  "
              f"{'NEW' if result['is_new'] else 'MERGED'}  "
              f"severity={result['severity']}  risk={result['risk_score']}"
              f"{'  ⚠️ GRIEVANCE FILED: ' + str(result.get('grievance_id','')) if result.get('grievance_filed') else ''}")
        return result
    except Exception as e:
        print(f"  ✗ POST failed: {e}")
        return None


def _phone_base_url(source) -> str | None:
    if not isinstance(source, str) or not _is_http_source(source):
        return None
    parsed = urlparse(source)
    return f"{parsed.scheme}://{parsed.netloc}"


def _extract_lat_lon(payload) -> tuple[float, float] | None:
    """Extract lat/lon values from nested JSON payloads."""
    found = {}

    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                key_l = str(key).lower()
                if key_l in ("lat", "latitude"):
                    try:
                        found["lat"] = float(value)
                    except Exception:
                        pass
                if key_l in ("lon", "lng", "longitude"):
                    try:
                        found["lon"] = float(value)
                    except Exception:
                        pass
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(payload)
    if "lat" in found and "lon" in found:
        return found["lat"], found["lon"]
    return None


def _fetch_phone_gps(source: str) -> tuple[float, float] | None:
    """Try common phone-camera endpoints that may expose GPS coordinates."""
    base = _phone_base_url(source)
    if not base:
        return None

    candidates = [
        f"{base}/gps.json",
        f"{base}/sensors.json",
        f"{base}/status.json",
    ]

    for endpoint in candidates:
        try:
            resp = httpx.get(endpoint, timeout=3)
            resp.raise_for_status()
            loc = _extract_lat_lon(resp.json())
            if loc:
                return loc
        except Exception:
            continue
    return None


def _draw_preview(frame: np.ndarray, detections: list[dict], posted: list[dict | None], lat: float, lon: float):
    """Draw bounding boxes and metadata onto the preview frame."""
    out = frame.copy()
    for idx, det in enumerate(detections):
        bbox = det.get("bbox") or []
        if len(bbox) != 4:
            continue

        x1, y1, x2, y2 = [int(v) for v in bbox]
        sev = str(det.get("severity_est", "low")).lower()
        conf = float(det.get("confidence", 0.0))
        klass = str(det.get("class_name", "pothole"))
        result = posted[idx] if idx < len(posted) else None

        color_map = {
            "low": (34, 197, 94),
            "medium": (234, 179, 8),
            "high": (249, 115, 22),
            "critical": (239, 68, 68),
        }
        color = color_map.get(sev, (34, 211, 238))

        cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)
        label = f"{klass} {sev} {conf:.2f}"
        if result:
            label += f" | id:{result.get('pothole_id')} risk:{result.get('risk_score')}"

        y_text = max(20, y1 - 8)
        cv2.putText(out, label, (x1, y_text), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2, cv2.LINE_AA)

    footer = f"Lat:{lat:.6f} Lon:{lon:.6f} Detections:{len(detections)}"
    cv2.putText(out, footer, (10, out.shape[0] - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (240, 240, 240), 2, cv2.LINE_AA)
    return out


def _is_http_source(source: str) -> bool:
    return isinstance(source, str) and source.startswith(("http://", "https://"))


def _build_ip_webcam_candidates(source: str) -> list[tuple[str, str]]:
    """Return candidate stream/snapshot endpoints for common phone camera apps."""
    if not _is_http_source(source):
        return []

    parsed = urlparse(source)
    base = f"{parsed.scheme}://{parsed.netloc}"
    path = parsed.path.rstrip("/")
    candidates: list[tuple[str, str]] = []

    def add(kind: str, url: str):
        item = (kind, url)
        if item not in candidates:
            candidates.append(item)

    if not path:
        add("stream", f"{base}/video")
        add("stream", f"{base}/videofeed")
        add("snapshot", f"{base}/shot.jpg")
        return candidates

    add("stream", source)
    if path.endswith("/video") or path.endswith("/videofeed"):
        add("snapshot", f"{base}/shot.jpg")
    elif path.endswith("/shot.jpg"):
        add("stream", f"{base}/video")
        add("stream", f"{base}/videofeed")
    return candidates


def _read_snapshot_frame(snapshot_url: str) -> np.ndarray | None:
    """Fetch one JPEG frame from a snapshot endpoint."""
    try:
        resp = httpx.get(snapshot_url, timeout=10)
        resp.raise_for_status()
        arr = np.frombuffer(resp.content, dtype=np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        return frame
    except Exception as exc:
        print(f"Snapshot fetch failed from {snapshot_url}: {exc}")
        return None


def _open_stream_capture(source) -> tuple[cv2.VideoCapture | None, str | None]:
    """Open a webcam/video/URL source, trying common phone stream endpoints."""
    if not isinstance(source, str) or not _is_http_source(source):
        cap = cv2.VideoCapture(source)
        return (cap if cap.isOpened() else None, None)

    for kind, candidate in _build_ip_webcam_candidates(source):
        if kind != "stream":
            continue
        cap = cv2.VideoCapture(candidate)
        if cap.isOpened():
            return cap, candidate
        cap.release()
    return None, None


def _iter_source_frames(source, snapshot_interval: float = 0.25):
    """Yield frames from webcam/video or snapshot endpoints."""
    cap, opened_source = _open_stream_capture(source)
    if cap is not None:
        try:
            while cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    break
                yield frame, opened_source or str(source)
        finally:
            cap.release()
        return

    if isinstance(source, str) and _is_http_source(source):
        for kind, candidate in _build_ip_webcam_candidates(source):
            if kind != "snapshot":
                continue
            print(f"Falling back to snapshot polling: {candidate}")
            while True:
                frame = _read_snapshot_frame(candidate)
                if frame is None:
                    break
                yield frame, candidate
                time.sleep(snapshot_interval)
            return

    raise RuntimeError(
        f"Cannot open source: {source}. For IP Webcam, confirm the phone and laptop are on the same Wi-Fi and try http://PHONE_IP:8080/video or http://PHONE_IP:8080/shot.jpg"
    )


def run_edge_client(args):
    detector = PotholeDetector(args.model, args.conf)
    api_url = args.api
    gps_track = load_gps_track(args.gps_track)

    source = args.source
    if source.isdigit():
        source = int(source)

    phone_gps = None
    phone_gps_last = 0.0

    # ── Image directory mode ──
    if isinstance(source, str) and os.path.isdir(source):
        images = sorted(glob.glob(os.path.join(source, "*.jpg")) +
                        glob.glob(os.path.join(source, "*.png")))
        print(f"Processing {len(images)} images from {source}")
        for i, img_path in enumerate(images):
            img = cv2.imread(img_path)
            if img is None:
                continue
            gps = gps_track[i] if i < len(gps_track) else {}
            lat = gps.get("lat", args.lat)
            lon = gps.get("lon", args.lon)
            print(f"\n[{i+1}/{len(images)}] {os.path.basename(img_path)} @ ({lat:.4f}, {lon:.4f})")

            dets = detector.detect_image(img, args.camera_id, lat, lon)
            print(f"  {len(dets)} detection(s)")
            for d in dets:
                post_detection(d, api_url)
            time.sleep(0.2)
        return

    frame_idx = 0
    gps_idx = 0
    print(f"Streaming from {source} — press Ctrl+C to stop")

    try:
        for frame, active_source in _iter_source_frames(source, args.snapshot_interval):
            frame_idx += 1
            if frame_idx % args.skip != 0:
                continue

            # GPS: cycle through track or use defaults
            if gps_track:
                gps = gps_track[gps_idx % len(gps_track)]
                gps_idx += 1
                lat, lon = gps["lat"], gps["lon"]
            else:
                if args.phone_gps and isinstance(source, str) and _is_http_source(source):
                    now = time.time()
                    if (now - phone_gps_last) >= args.phone_gps_interval:
                        phone_gps = _fetch_phone_gps(source)
                        phone_gps_last = now
                        if phone_gps:
                            print(f"Using phone GPS: ({phone_gps[0]:.6f}, {phone_gps[1]:.6f})")
                lat, lon = phone_gps if phone_gps else (args.lat, args.lon)

            dets = detector.detect_image(frame, args.camera_id, lat, lon)
            if dets:
                print(f"\n[Frame {frame_idx}] {len(dets)} detection(s) @ ({lat:.4f}, {lon:.4f}) from {active_source}")
                posted_results = []
                for d in dets:
                    posted_results.append(post_detection(d, api_url))
            else:
                posted_results = []

            if args.preview:
                preview = _draw_preview(frame, dets, posted_results, lat, lon)
                cv2.imshow("PotholeGuard Live Detection", preview)
                key = cv2.waitKey(1) & 0xFF
                if key in (ord("q"), 27):
                    print("Preview stopped by user")
                    break
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nStopped by user")
    except cv2.error as exc:
        print(f"OpenCV preview error: {exc}. Run without --preview in a headless environment.")
    except RuntimeError as exc:
        print(str(exc))
    finally:
        if args.preview:
            cv2.destroyAllWindows()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Edge pothole detection client")
    parser.add_argument("--source", default="0", help="Webcam id, stream URL, video path, or image dir")
    parser.add_argument("--model", default="yolov8n.pt", help="YOLO model path")
    parser.add_argument("--conf", type=float, default=0.25, help="Confidence threshold")
    parser.add_argument("--api", default="http://localhost:8000", help="Backend API URL")
    parser.add_argument("--camera-id", default=settings.camera_id)
    parser.add_argument("--lat", type=float, default=settings.default_lat)
    parser.add_argument("--lon", type=float, default=settings.default_lon)
    parser.add_argument("--skip", type=int, default=5, help="Process every Nth frame")
    parser.add_argument("--preview", action="store_true", help="Show live frame preview with highlighted detections")
    parser.add_argument("--phone-gps", action="store_true", help="Try to read GPS coordinates from the phone camera host")
    parser.add_argument("--phone-gps-interval", type=float, default=3.0, help="Seconds between phone GPS fetch attempts")
    parser.add_argument("--gps-track", default=None, help="JSON file with GPS coordinates")
    parser.add_argument("--snapshot-interval", type=float, default=0.35, help="Seconds between IP camera snapshot polls")
    args = parser.parse_args()

    run_edge_client(args)
