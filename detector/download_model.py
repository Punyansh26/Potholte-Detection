"""Download a pretrained YOLOv8 pothole detection model.

Uses the Roboflow public inference API or downloads a model from
a public source. Run this once before starting the backend.

Usage:
    python detector/download_model.py
"""

import os
import sys
import urllib.request
import zipfile
import shutil

# ─────────────────────────────────────────────────────────────────────────────
# Option 1: Download from a public Roboflow-exported YOLO model
# (replace with your own if you have a Roboflow account)
# ─────────────────────────────────────────────────────────────────────────────

ROBOFLOW_API_URL = (
    "https://universe.roboflow.com/ds/XXXXXXXX"  # placeholder
)

# ─────────────────────────────────────────────────────────────────────────────
# Option 2: Use Ultralytics Hub / auto-download a suitable public model
# We use a YOLO model fine-tuned for roads / cracks / potholes from HuggingFace
# ─────────────────────────────────────────────────────────────────────────────

HF_MODEL_URL = (
    "https://huggingface.co/keremberke/yolov8n-pothole-segmentation"
    "/resolve/main/best.pt"
)

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "..", "models", "pothole.pt")


def download_hf(url: str, dest: str):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    print(f"Downloading from HuggingFace:\n  {url}")
    print(f"Saving to: {dest}")
    try:
        urllib.request.urlretrieve(url, dest, reporthook=_progress)
        print("\nDone!")
        return True
    except Exception as e:
        print(f"\nFailed: {e}")
        return False


def _progress(block, block_size, total):
    downloaded = block * block_size
    if total > 0:
        pct = min(100, downloaded * 100 // total)
        bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
        print(f"\r  [{bar}] {pct}%", end="", flush=True)


if __name__ == "__main__":
    success = download_hf(HF_MODEL_URL, OUTPUT_PATH)
    if success:
        abs_path = os.path.abspath(OUTPUT_PATH)
        print(f"\nSet YOLO_MODEL env var to use this model:")
        print(f"  Windows:  $env:YOLO_MODEL = '{abs_path}'")
        print(f"  Linux:    export YOLO_MODEL='{abs_path}'")
        print(f"\nOr add to your .env file:")
        print(f"  YOLO_MODEL={abs_path}")
    else:
        print("\nAlternative: use Roboflow hosted inference (see below)")
        print("  pip install inference")
        print("  # Get free API key at https://app.roboflow.com")
        sys.exit(1)
