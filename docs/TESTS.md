# Testing & Evaluation Plan

## Running Tests

```bash
# All tests
python -m pytest tests/ -v --tb=short

# Individual suites
python -m pytest tests/test_api.py -v           # API endpoints
python -m pytest tests/test_dedup.py -v          # Spatial deduplication
python -m pytest tests/test_grievance.py -v      # Risk scoring + grievance
python -m pytest tests/test_verification.py -v   # Repair verification
```

---

## Test Coverage

### Unit Tests
| Test | File | What it verifies |
|------|------|-----------------|
| Health endpoint | `test_api.py` | GET /health returns 200 |
| POST detection | `test_api.py` | Creates pothole, returns ID |
| Detection with snapshot | `test_api.py` | Base64 image saves correctly |
| List potholes (empty) | `test_api.py` | Returns [] when no data |
| List potholes (populated) | `test_api.py` | Returns detections after POST |
| Filter by severity | `test_api.py` | Query param filtering works |
| Pothole detail | `test_api.py` | GET /potholes/{id} returns full detail |
| Pothole not found | `test_api.py` | 404 for missing ID |
| Manual report | `test_api.py` | POST /manual_report creates entry |
| Mock CPGRAMS submit | `test_api.py` | Returns CPGRAMS-XXX ticket ID |
| Mock CPGRAMS status | `test_api.py` | Status query works |
| Mock CPGRAMS list | `test_api.py` | List all tickets |

### Integration Tests
| Test | File | What it verifies |
|------|------|-----------------|
| Merge within 2.5m | `test_dedup.py` | Two reports → same Pothole_ID |
| Separate > 2.5m | `test_dedup.py` | Two reports → different IDs |
| Detection count update | `test_dedup.py` | 3 merges → count=3 |
| Haversine accuracy | `test_dedup.py` | ~111m per degree latitude |

### Scoring & Grievance Tests
| Test | File | What it verifies |
|------|------|-----------------|
| Severity levels | `test_grievance.py` | low/medium/high/critical from bbox |
| Risk score range | `test_grievance.py` | 0–100 output |
| Auto-file threshold | `test_grievance.py` | Critical + high conf ≥ 80 |
| CPGRAMS payload | `test_grievance.py` | Correct structure |

### Verification Tests
| Test | File | What it verifies |
|------|------|-----------------|
| Identical images | `test_verification.py` | Not marked repaired |
| Different images | `test_verification.py` | Marked repaired |
| No previous image | `test_verification.py` | Graceful fallback |
| Image comparison | `test_verification.py` | Returns (SSIM, match_count) |

---

## Model Evaluation

For model accuracy testing (requires trained model + labeled test set):

```bash
python -c "
from ultralytics import YOLO
model = YOLO('runs/pothole/train/weights/best.pt')
metrics = model.val(data='datasets/potholes/pothole.yaml')
print(f'mAP@0.5: {metrics.box.map50:.3f}')
print(f'Precision: {metrics.box.mp:.3f}')
print(f'Recall: {metrics.box.mr:.3f}')
"
```

### Targets
| Metric | Target | Notes |
|--------|--------|-------|
| mAP@0.5 | ≥ 0.80 | Overall detection quality |
| Precision | ≥ 0.80 | Low false positive rate |
| Recall | ≥ 0.75 | Catch most potholes |
| FPS (laptop CPU) | ≥ 5 | Usable real-time |
| FPS (GPU) | ≥ 30 | Smooth real-time |

---

## Performance Test

```bash
python -c "
import time, cv2
from detector.inference import PotholeDetector
d = PotholeDetector('yolov8n.pt')
cap = cv2.VideoCapture(0)
times = []
for _ in range(100):
    ret, frame = cap.read()
    if not ret: break
    t0 = time.time()
    d.detect_image(frame)
    times.append(time.time() - t0)
cap.release()
fps = 1 / (sum(times)/len(times))
print(f'Avg FPS: {fps:.1f}')
print(f'Avg latency: {sum(times)/len(times)*1000:.1f}ms')
"
```
