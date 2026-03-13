"""Export a trained YOLOv8 model to ONNX (and optionally TFLite / TensorRT).

Usage:
  python detector/export_onnx.py --model runs/pothole/train/weights/best.pt
"""

from __future__ import annotations

import argparse
from ultralytics import YOLO


def export(model_path: str, fmt: str = "onnx", imgsz: int = 640):
    model = YOLO(model_path)
    out = model.export(format=fmt, imgsz=imgsz, simplify=True)
    print(f"Exported to: {out}")
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export YOLOv8 model")
    parser.add_argument("--model", required=True, help="Path to .pt model")
    parser.add_argument("--format", default="onnx", choices=["onnx", "tflite", "engine"])
    parser.add_argument("--imgsz", type=int, default=640)
    args = parser.parse_args()

    export(args.model, args.format, args.imgsz)
