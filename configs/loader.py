from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


CONFIG_DIR = Path(__file__).resolve().parent


def load_config(name: str) -> dict[str, Any]:
    """Load a versioned YAML configuration from the configs directory."""
    path = CONFIG_DIR / name
    if not path.is_file():
        raise FileNotFoundError(f"Configuration file not found: {path}")

    with path.open(encoding="utf-8") as file:
        config = yaml.safe_load(file)

    if not isinstance(config, dict):
        raise ValueError(f"Configuration must contain a YAML mapping: {path}")
    return config


def parse_time(value: str):
    """Convert an HH:MM configuration value into a datetime.time."""
    import datetime as dt

    return dt.time.fromisoformat(value)

