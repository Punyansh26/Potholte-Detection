"""Application configuration loaded from environment variables."""

import os
from pathlib import Path
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

    # Deduplication
    dedup_radius_meters: float = 2.5

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()

# Ensure storage directory exists
Path(settings.storage_path).mkdir(parents=True, exist_ok=True)
