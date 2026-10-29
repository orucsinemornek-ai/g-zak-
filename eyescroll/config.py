from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PROJECT_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_DIR / "config.json"

DEFAULTS: dict[str, Any] = {
    "controller": "active",
    "target_monitor": 0,
    "prefer_foreground": True,
    "use_wheel": False,
    "camera_index": 0,
    "detector": "auto",
    "threshold_ratio": 0.8,
    "ear_baseline": None,
    "ear_closed": None,
    "min_closed_ms": 400,
    "cooldown_ms": 1200,
    "scroll_down_key": "PageDown",
    "scroll_up_key": "PageUp",
    "debug_port": 9222,
    "cdp_timeout_s": 10,
    "show_preview": True,
    "calibration_seconds": 5,
}


class Config:
    def __init__(self, data: dict[str, Any], path: Path):
        self._data = data
        self.path = path

    @classmethod
    def load(cls, path: Path | None = None) -> "Config":
        path = path or CONFIG_PATH
        data = dict(DEFAULTS)
        if path.exists():
            with path.open("r", encoding="utf-8-sig") as fh:
                loaded = json.load(fh)
            data.update(loaded)
        else:
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return cls(data, path)

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def save(self) -> None:
        self.path.write_text(json.dumps(self._data, indent=2), encoding="utf-8")

    def as_dict(self) -> dict[str, Any]:
        return dict(self._data)

