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
                lat, lon = args.lat, args.lon

            dets = detector.detect_image(frame, args.camera_id, lat, lon)
            if dets:
                print(f"\n[Frame {frame_idx}] {len(dets)} detection(s) @ ({lat:.4f}, {lon:.4f}) from {active_source}")
                for d in dets:
                    post_detection(d, api_url)
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nStopped by user")
    except RuntimeError as exc:
        print(str(exc))
    finally:
        pass


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
    parser.add_argument("--gps-track", default=None, help="JSON file with GPS coordinates")
    parser.add_argument("--snapshot-interval", type=float, default=0.35, help="Seconds between IP camera snapshot polls")
    args = parser.parse_args()

    run_edge_client(args)
