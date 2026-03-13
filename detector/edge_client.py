"""Edge detection client — runs inference and POSTs detections to the backend.

Usage examples:
  # Webcam
  python detector/edge_client.py --source 0

  # Video file
  python detector/edge_client.py --source dashcam.mp4

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
import httpx
import cv2

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

    # ── Video / webcam mode ──
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        print(f"Cannot open source: {source}")
        return

    frame_idx = 0
    gps_idx = 0
    print(f"Streaming from {source} — press Ctrl+C to stop")

    try:
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
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
                print(f"\n[Frame {frame_idx}] {len(dets)} detection(s) @ ({lat:.4f}, {lon:.4f})")
                for d in dets:
                    post_detection(d, api_url)
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nStopped by user")
    finally:
        cap.release()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Edge pothole detection client")
    parser.add_argument("--source", default="0", help="Webcam id, video path, or image dir")
    parser.add_argument("--model", default="yolov8n.pt", help="YOLO model path")
    parser.add_argument("--conf", type=float, default=0.25, help="Confidence threshold")
    parser.add_argument("--api", default="http://localhost:8000", help="Backend API URL")
    parser.add_argument("--camera-id", default=settings.camera_id)
    parser.add_argument("--lat", type=float, default=settings.default_lat)
    parser.add_argument("--lon", type=float, default=settings.default_lon)
    parser.add_argument("--skip", type=int, default=5, help="Process every Nth frame")
    parser.add_argument("--gps-track", default=None, help="JSON file with GPS coordinates")
    args = parser.parse_args()

    run_edge_client(args)
