"""Load one or more days from both APIs into the raw schema."""

from __future__ import annotations

import datetime as dt
import logging
from concurrent.futures import ThreadPoolExecutor
from functools import partial

import psycopg
import requests

from airquality import warehouse
from airquality.config import Coverage
from airquality.gios import GiosClient
from airquality.openmeteo import hourly_weather

log = logging.getLogger(__name__)

# The archive endpoint can take 10-20 s for a sensor it has not served recently.
# A few requests at a time keep a daily load to minutes without leaning on a free API.
FETCH_WORKERS = 4


class NoDataError(RuntimeError):
    """The APIs answered, with nothing for the requested days."""


def ingest_air_quality(conn: psycopg.Connection, client: GiosClient, coverage: Coverage,
                       first_day: dt.date, last_day: dt.date, workers: int = FETCH_WORKERS) -> dict[str, int]:
    """Stations and sensors of the covered cities, then their hourly results for the days."""
    cities = {city.name for city in coverage.cities}
    stations = [s for s in client.stations() if s.city in cities]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        sensors = [
            sensor
            for found in pool.map(client.sensors, [s.station_id for s in stations])
            for sensor in found
            if sensor.pollutant_code in coverage.pollutants
        ]
        counts = {
            "stations": warehouse.upsert_stations(conn, stations),
            "sensors": warehouse.upsert_sensors(conn, sensors),
            "measurements": 0,      # hourly results read from the API
            "changed": 0,           # of those, new or different from what was stored
        }
        conn.commit()
        # the requests run in the pool; the rows are written here, in order, on the one connection
        fetch = partial(client.measurements, first_day=first_day, last_day=last_day)
        newest: dt.datetime | None = None
        for done, results in enumerate(pool.map(fetch, [s.sensor_id for s in sensors]), start=1):
            # PM and benzene are also sampled by hand on filters: one value a day, code ending in -24g
            hourly = [m for m in results if m.is_hourly]
            counts["measurements"] += len(hourly)
            counts["changed"] += warehouse.upsert_measurements(conn, hourly)
            if hourly:
                latest = max(m.measured_at_cet for m in hourly)
                newest = latest if newest is None else max(newest, latest)
            conn.commit()          # per sensor: an interrupted load keeps what it already has
            if done % 25 == 0:
                log.info("GIOS: %s of %s sensors, %s results so far",
                         done, len(sensors), counts["measurements"])
    log.info("GIOS %s to %s: %s", first_day, last_day, counts)
    if newest is None or newest.date() < last_day:
        # every request succeeded and none had a result for the last day: it is not published
        # yet, or the API is answering with empty lists. Either way the load did not happen.
        raise NoDataError(f"no hourly results from {len(sensors)} sensors for {last_day}"
                          f" (newest result: {newest or 'none'})")
    return counts


def ingest_weather(conn: psycopg.Connection, coverage: Coverage, first_day: dt.date, last_day: dt.date,
                   session: requests.Session | None = None, today: dt.date | None = None) -> int:
    # The air-quality day is a CET day, which starts at 23:00 UTC the day before.
    # Asking from one day earlier gives every measured hour its weather.
    start = first_day - dt.timedelta(days=1)
    rows = 0
    for city in coverage.cities:
        hours = hourly_weather(city.latitude, city.longitude, start, last_day,
                               session=session, today=today)
        rows += warehouse.upsert_weather(conn, city.name, hours)
    conn.commit()
    log.info("Open-Meteo %s to %s: %s rows", start, last_day, rows)
    return rows
