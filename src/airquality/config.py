"""Settings: which cities and pollutants, and where the warehouse is."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG_FILE = Path(os.environ.get("AIRQUALITY_CONFIG", ROOT / "config" / "cities.yml"))
RAW_SCHEMA_FILE = Path(os.environ.get("AIRQUALITY_RAW_SCHEMA", ROOT / "sql" / "raw_schema.sql"))


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


def warehouse_conninfo() -> str:
    env = os.environ.get
    return (
        f"host={env('WAREHOUSE_HOST', 'localhost')} port={env('WAREHOUSE_PORT', '5435')} "
        f"dbname={env('WAREHOUSE_DB', 'warehouse')} user={env('WAREHOUSE_USER', 'airquality')} "
        f"password={env('WAREHOUSE_PASSWORD', 'airquality')}"
    )
