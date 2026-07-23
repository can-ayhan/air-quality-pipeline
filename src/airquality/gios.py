"""Client for the GIOS air-quality API (Chief Inspectorate of Environmental Protection, Poland).

API: https://api.gios.gov.pl/pjp-api/v1/rest (JSON-LD, Polish field names, paged).

Three calls are used:

* station/findAll                            every measuring station
* station/sensors/{station}                  the sensors ("stanowiska") of a station, one per pollutant
* archivalData/getDataBySensor/{sensor}      measurements of a sensor for a date range

Hourly results from the archival endpoint are in CET (UTC+1) all year, without
daylight saving. The client returns them as naive datetimes in that clock and
leaves the conversion to UTC to the warehouse, where it is visible and tested.
"""

from __future__ import annotations

import datetime as dt
import logging
import time
from dataclasses import dataclass, replace

import requests

log = logging.getLogger(__name__)

BASE_URL = "https://api.gios.gov.pl/pjp-api/v1/rest"
PAGE_SIZE = 500

# keys of the lists in the responses
STATIONS = "Lista stacji pomiarowych"
SENSORS = "Lista stanowisk pomiarowych dla podanej stacji"
MEASUREMENTS = "Lista archiwalnych wyników pomiarów"


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


@dataclass(frozen=True)
class Measurement:
    sensor_id: int
    sensor_code: str         # e.g. MzWarAlNiepo-PM10-1g; the suffix is the averaging time
    measured_at_cet: dt.datetime
    value: float | None      # None: the hour exists but has no valid result

    @property
    def is_hourly(self) -> bool:
        return self.sensor_code.endswith("-1g")


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


def parse_measurement(sensor_id: int, item: dict) -> Measurement:
    value = item.get("Wartość")
    return Measurement(
        sensor_id=sensor_id,
        sensor_code=item["Kod stanowiska"],
        measured_at_cet=dt.datetime.strptime(item["Data"], "%Y-%m-%d %H:%M:%S"),
        value=None if value is None else float(value),
    )


def untangle_clock_change(results: list[Measurement]) -> list[Measurement]:
    """Give the hour of the spring clock change its own timestamp back.

    The results are in CET, which has no clock change. Even so, for the last
    Sunday of March the archive has no result at 02:00 and two at 03:00 (every
    sensor on 2026-03-29). The list is in time order, so the first of the two is
    the 02:00 result. Left alone, the two overwrite each other on the key: the
    day has 23 hours and every reload flips the value at 03:00.
    """
    fixed: list[Measurement] = []
    for result in results:
        previous = fixed[-1] if fixed else None
        same_stamp = previous is not None and previous.measured_at_cet == result.measured_at_cet
        if same_stamp and previous.sensor_code == result.sensor_code:
            hour_before = result.measured_at_cet - dt.timedelta(hours=1)
            if len(fixed) < 2 or fixed[-2].measured_at_cet < hour_before:
                fixed[-1] = replace(previous, measured_at_cet=hour_before)
        fixed.append(result)
    return fixed


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

    def measurements(self, sensor_id: int, first_day: dt.date, last_day: dt.date) -> list[Measurement]:
        """All results of a sensor from 00:00 on first_day to 23:00 on last_day (CET)."""
        params = {"dateFrom": f"{first_day:%Y-%m-%d} 00:00", "dateTo": f"{last_day:%Y-%m-%d} 23:00"}
        items = self._all_pages(f"archivalData/getDataBySensor/{sensor_id}", MEASUREMENTS, params)
        return untangle_clock_change([parse_measurement(sensor_id, item) for item in items])
