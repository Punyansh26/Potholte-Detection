# Model Training & Deployment Guide

## Dataset

### Recommended Sources
- **Roboflow Universe**: [Pothole Detection datasets](https://universe.roboflow.com/search?q=pothole)
- **Kaggle**: Search "pothole detection"
- **Custom**: capture with dashcam/phone and annotate with [Roboflow](https://roboflow.com) or [CVAT](https://www.cvat.ai/)

### Dataset Structure
```
datasets/potholes/
├── images/
│   ├── train/
│   └── val/
├── labels/
│   ├── train/
│   └── val/
└── pothole.yaml
```

**pothole.yaml:**
```yaml
path: ./datasets/potholes
train: images/train
val: images/val
nc: 1
names: ['pothole']
```

### Important Notes
- Include **negative samples**: manhole covers, dark patches, shadows, parked cars
- Minimum 500 images recommended; 1000+ for robust performance
- 80/20 train/val split

---

## Training

```bash
python detector/train.py \
  --dataset datasets/potholes/pothole.yaml \
  --model yolov8s.pt \
  --epochs 50 \
  --imgsz 640 \
  --batch 16
```

### Augmentations (built-in)
- HSV jitter (hue, saturation, brightness)
- Random rotation (±10°), translation, scale, shear
- Horizontal flip, mosaic, mixup
- Add custom: rain simulation, night/dawn lighting via Albumentations

### Targets
- **mAP@0.5** ≥ 0.80
- **Precision** ≥ 0.80
- **Recall** ≥ 0.75

Training curves saved in `runs/pothole/train/`.

---

## Export to Edge

### ONNX
```bash
python detector/export_onnx.py --model runs/pothole/train/weights/best.pt --format onnx
```

### TensorRT (Jetson)
```bash
python detector/export_onnx.py --model best.pt --format engine
```

### TFLite (Mobile)
```bash
python detector/export_onnx.py --model best.pt --format tflite
```

---

## Inference

```bash
# Single image
python detector/inference.py --source pothole.jpg --model best.pt

# Video
python detector/inference.py --source dashcam.mp4 --model best.pt --skip 5

# Webcam
python detector/inference.py --source 0 --model best.pt
```

---

## Edge Deployment (Jetson Nano)

1. Export model to TensorRT: `python detector/export_onnx.py --model best.pt --format engine`
2. Copy `.engine` file to Jetson
3. Run: `python detector/edge_client.py --model best.engine --source 0`

FPS target: 10–15 on Jetson Nano with YOLOv8n.
