"""Application configuration loaded from environment variables."""

import os
import sys
from pathlib import Path
from pydantic import ConfigDict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "sqlite:///./pothole.db"

    # Storage
    storage_path: str = "./storage/snapshots"

    # Grievance
    cpgrams_endpoint: str = "http://localhost:8000/mock/cpgrams/grievance"
    risk_threshold: int = 80

    # Detection defaults
    default_lat: float = 19.0760
    default_lon: float = 72.8777
    camera_id: str = "edge-001"
    yolo_model: str = "keremberke/yolov8n-pothole-segmentation"
    yolo_conf: float = 0.25
    yolo_iou: float = 0.45
    yolo_agnostic_nms: bool = False
    yolo_max_det: int = 1000

    # Deduplication
    dedup_radius_meters: float = 2.5

    model_config = ConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()

if "pytest" in sys.modules:
    settings.database_url = os.environ.get("TEST_DATABASE_URL", "sqlite:///./test_pothole.db")

# Ensure storage directory exists
Path(settings.storage_path).mkdir(parents=True, exist_ok=True)
