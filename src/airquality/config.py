"""Settings: which cities and pollutants the pipeline covers."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG_FILE = Path(os.environ.get("AIRQUALITY_CONFIG", ROOT / "config" / "cities.yml"))


@dataclass(frozen=True)
class City:
    name: str
    latitude: float
    longitude: float


@dataclass(frozen=True)
class Coverage:
    cities: list[City]
    pollutants: list[str]


def load_coverage(path: Path = CONFIG_FILE) -> Coverage:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return Coverage([City(**city) for city in data["cities"]], list(data["pollutants"]))
