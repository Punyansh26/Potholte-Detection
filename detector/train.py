"""YOLOv8 training script for pothole detection.

Usage:
  python detector/train.py --dataset path/to/pothole.yaml --epochs 50

Dataset YAML example (pothole.yaml):
  path: ./datasets/potholes
  train: images/train
  val: images/val
  nc: 1
  names: ['pothole']
"""

from __future__ import annotations

import argparse
from pathlib import Path

from ultralytics import YOLO


def train(
    dataset: str,
    model: str = "yolov8s.pt",
    epochs: int = 50,
    imgsz: int = 640,
    batch: int = 16,
    project: str = "runs/pothole",
    name: str = "train",
):
    """Fine‑tune a YOLOv8 model on a pothole dataset."""

    model_obj = YOLO(model)

    # Augmentation‑rich training config
    results = model_obj.train(
        data=dataset,
        epochs=epochs,
        imgsz=imgsz,
        batch=batch,
        project=project,
        name=name,
        # Augmentations
        hsv_h=0.015,     # hue shift
        hsv_s=0.7,       # saturation
        hsv_v=0.4,       # brightness
        degrees=10,       # rotation
        translate=0.1,
        scale=0.5,
        shear=5,
        flipud=0.0,
        fliplr=0.5,
        mosaic=1.0,
        mixup=0.1,
        # Various
        patience=15,
        save=True,
        save_period=10,
        plots=True,
        verbose=True,
    )

    print("\n═══ Training Complete ═══")
    print(f"Best model saved to: {results.save_dir / 'weights/best.pt'}")
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train YOLOv8 pothole detector")
    parser.add_argument("--dataset", required=True, help="Path to dataset YAML")
    parser.add_argument("--model", default="yolov8s.pt", help="Base model")
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--project", default="runs/pothole")
    parser.add_argument("--name", default="train")
    args = parser.parse_args()

    train(
        dataset=args.dataset,
        model=args.model,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        project=args.project,
        name=args.name,
    )
