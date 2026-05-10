"""Client for Open-Meteo hourly weather (https://open-meteo.com, free, no key).

Two endpoints serve the same variables:

* api.open-meteo.com/v1/forecast          recent days (about three months back) and the forecast
* archive-api.open-meteo.com/v1/archive   reanalysis for anything older

The daily run reads yesterday from the first. A backfill of older dates has to
go to the second, so the client picks by the age of the requested range.
All times are requested and returned in UTC.
"""

from __future__ import annotations

import datetime as dt
import logging
import time
from dataclasses import dataclass

import requests

log = logging.getLogger(__name__)

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
RECENT_DAYS = 80          # the forecast endpoint goes back about 92 days; stay clear of the edge

VARIABLES = [
    "temperature_2m", "relative_humidity_2m", "wind_speed_10m", "wind_direction_10m",
    "precipitation", "surface_pressure",
]


class OpenMeteoError(RuntimeError):
    pass


@dataclass(frozen=True)
class WeatherHour:
    time_utc: dt.datetime
    temperature_c: float | None
    relative_humidity_pct: float | None
    wind_speed_ms: float | None
    wind_direction_deg: float | None
    precipitation_mm: float | None
    surface_pressure_hpa: float | None


def endpoint_for(first_day: dt.date, today: dt.date | None = None) -> str:
    today = today or dt.datetime.now(dt.UTC).date()
    return FORECAST_URL if (today - first_day).days <= RECENT_DAYS else ARCHIVE_URL


def parse_hourly(body: dict) -> list[WeatherHour]:
    hourly = body.get("hourly") or {}
    times = hourly.get("time") or []
    columns = [hourly.get(name) or [None] * len(times) for name in VARIABLES]
    return [
        WeatherHour(dt.datetime.fromisoformat(stamp), *values)
        for stamp, *values in zip(times, *columns, strict=True)
    ]


def hourly_weather(latitude: float, longitude: float, first_day: dt.date, last_day: dt.date,
                   session: requests.Session | None = None, today: dt.date | None = None,
                   max_retries: int = 4) -> list[WeatherHour]:
    url = endpoint_for(first_day, today)
    params = {
        "latitude": latitude, "longitude": longitude, "hourly": ",".join(VARIABLES),
        "start_date": first_day.isoformat(), "end_date": last_day.isoformat(),
        "timezone": "UTC", "wind_speed_unit": "ms",
    }
    session = session or requests.Session()
    for attempt in range(1, max_retries + 1):
        try:
            response = session.get(url, params=params, timeout=40)
        except requests.RequestException as exc:
            if attempt == max_retries:
                raise OpenMeteoError(f"{url}: {exc}") from exc
        else:
            if response.status_code == 200:
                return parse_hourly(response.json())
            if response.status_code not in (429, 500, 502, 503, 504) or attempt == max_retries:
                raise OpenMeteoError(f"{url}: HTTP {response.status_code} {response.text[:200]}")
        wait = 2 ** attempt
        log.warning("Open-Meteo request failed (attempt %s of %s), retrying in %s s",
                    attempt, max_retries, wait)
        time.sleep(wait)
    raise AssertionError("unreachable")
