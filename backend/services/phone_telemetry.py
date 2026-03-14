"""In-memory storage for the latest phone telemetry packet."""

from __future__ import annotations

from threading import Lock
from typing import Any

_latest_lock = Lock()
_latest_payload: dict[str, Any] | None = None


def set_latest(payload: dict[str, Any]) -> None:
    global _latest_payload
    with _latest_lock:
        _latest_payload = payload.copy()


def get_latest() -> dict[str, Any] | None:
    with _latest_lock:
        return _latest_payload.copy() if _latest_payload else None
