"""Client for the GIOS air-quality API (Chief Inspectorate of Environmental Protection, Poland).

API: https://api.gios.gov.pl/pjp-api/v1/rest (JSON-LD, Polish field names, paged).

Two calls so far:

* station/findAll                 every measuring station
* station/sensors/{station}       the sensors ("stanowiska") of a station, one per pollutant
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import requests

log = logging.getLogger(__name__)

BASE_URL = "https://api.gios.gov.pl/pjp-api/v1/rest"
PAGE_SIZE = 500

# keys of the lists in the responses
STATIONS = "Lista stacji pomiarowych"
SENSORS = "Lista stanowisk pomiarowych dla podanej stacji"


class GiosError(RuntimeError):
    """The API answered, but not with something usable."""


@dataclass(frozen=True)
class Station:
    station_id: int
    code: str
    name: str
    city: str
    voivodeship: str
    street: str | None
    latitude: float
    longitude: float


@dataclass(frozen=True)
class Sensor:
    sensor_id: int
    station_id: int
    pollutant_code: str      # PM10, PM2.5, NO2, ...
    pollutant_name: str      # Polish name as published


def parse_station(item: dict) -> Station:
    return Station(
        station_id=int(item["Identyfikator stacji"]),
        code=item["Kod stacji"],
        name=item["Nazwa stacji"],
        city=item["Nazwa miasta"],
        voivodeship=item["Województwo"],
        street=item.get("Ulica") or None,
        latitude=float(item["WGS84 φ N"]),
        longitude=float(item["WGS84 λ E"]),
    )


def parse_sensor(item: dict) -> Sensor:
    return Sensor(
        sensor_id=int(item["Identyfikator stanowiska"]),
        station_id=int(item["Identyfikator stacji"]),
        pollutant_code=item["Wskaźnik - kod"],
        pollutant_name=item["Wskaźnik"],
    )


class GiosClient:
    def __init__(self, session: requests.Session | None = None, base_url: str = BASE_URL,
                 pause: float = 0.15, max_retries: int = 4, timeout: float = 40):
        self.session = session or requests.Session()
        self.base_url = base_url.rstrip("/")
        self.pause = pause               # the API is free and unauthenticated: do not hammer it
        self.max_retries = max_retries
        self.timeout = timeout

    def _get(self, path: str, params: dict) -> dict:
        url = f"{self.base_url}/{path}"
        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.session.get(url, params=params, timeout=self.timeout)
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    raise GiosError(f"{url}: {exc}") from exc
                wait = 2 ** attempt
            else:
                if response.status_code == 200:
                    time.sleep(self.pause)
                    return response.json()
                if response.status_code not in (429, 500, 502, 503, 504) or attempt == self.max_retries:
                    raise GiosError(f"{url}: HTTP {response.status_code} {response.text[:200]}")
                wait = float(response.headers.get("Retry-After", 2 ** attempt))
            log.warning("GIOS request failed (attempt %s of %s), retrying in %.0f s: %s",
                        attempt, self.max_retries, wait, url)
            time.sleep(wait)
        raise AssertionError("unreachable")

    def _all_pages(self, path: str, key: str, params: dict | None = None) -> list[dict]:
        items: list[dict] = []
        page = 0
        while True:
            body = self._get(path, {**(params or {}), "page": page, "size": PAGE_SIZE})
            items.extend(body.get(key) or [])
            page += 1
            if page >= int(body.get("totalPages") or 1):
                return items

    def stations(self) -> list[Station]:
        return [parse_station(item) for item in self._all_pages("station/findAll", STATIONS)]

    def sensors(self, station_id: int) -> list[Sensor]:
        return [parse_sensor(item) for item in self._all_pages(f"station/sensors/{station_id}", SENSORS)]
