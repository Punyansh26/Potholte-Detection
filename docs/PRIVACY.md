# Privacy by Design

## Principles

This system follows **Privacy by Design** principles aligned with India's **Digital Personal Data Protection Act (DPDP) 2023**.

## Data Minimization

| Data Type | Handling |
|-----------|----------|
| Video stream | Processed **on-device only** — never uploaded |
| Snapshots | Only **cropped asphalt region** around detection is saved |
| GPS coordinates | Logged **only on positive detection** — no continuous tracking |
| Audio | **Not captured** at any point |
| Vehicle routes | **Not stored** — only individual pothole location points |

## PII Scrubbing Pipeline

Before any image leaves the device:

1. **Face Detection**: OpenCV Haar cascade (`haarcascade_frontalface_default.xml`)
2. **License Plate Detection**: OpenCV Haar cascade (`haarcascade_russian_plate_number.xml`)
3. **Irreversible Blur**: Heavy Gaussian blur (kernel 51×51, σ=30) applied to detected regions
4. Only the blurred image is uploaded

### Usage
```python
from privacy.blur import blur_pii
import cv2

img = cv2.imread("snapshot.jpg")
clean = blur_pii(img)  # faces & plates blurred
cv2.imwrite("clean_snapshot.jpg", clean)
```

### CLI
```bash
python privacy/blur.py input.jpg output_blurred.jpg
```

## DPDP Compliance Basics

- **Lawful Purpose**: Pothole detection serves public safety (road infrastructure monitoring)
- **Data Minimization**: Only defect-relevant data is collected
- **No Personal Data**: After blur pipeline, no personally identifiable information remains
- **Retention**: Snapshots are retained only while pothole is active; purged 30 days after repair
- **Access**: No user accounts or personal data collected from reporters (manual reports are anonymous)
- **Security**: All data stored locally or in controlled infrastructure; HTTPS for API communication

## Checklist

- [x] Process video on-device; only upload cropped asphalt images
- [x] Face detector + irreversible blur before network transfer
- [x] License plate detector + irreversible blur before network transfer
- [x] No audio capture
- [x] No continuous vehicle route logging
- [x] DB entry created only on positive detection
- [x] Anonymous manual reporting (no user PII collected)
