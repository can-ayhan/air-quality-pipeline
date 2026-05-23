"""Load one or more days from both APIs into the raw schema."""

from __future__ import annotations

import datetime as dt
import logging

import psycopg
import requests

from airquality import warehouse
from airquality.config import Coverage
from airquality.gios import GiosClient
from airquality.openmeteo import hourly_weather

log = logging.getLogger(__name__)


def ingest_air_quality(conn: psycopg.Connection, client: GiosClient, coverage: Coverage,
                       first_day: dt.date, last_day: dt.date) -> dict[str, int]:
    """Stations and sensors of the covered cities, then their hourly results for the days."""
    cities = {city.name for city in coverage.cities}
    stations = [s for s in client.stations() if s.city in cities]
    sensors = [
        sensor
        for station in stations
        for sensor in client.sensors(station.station_id)
        if sensor.pollutant_code in coverage.pollutants
    ]
    counts = {
        "stations": warehouse.upsert_stations(conn, stations),
        "sensors": warehouse.upsert_sensors(conn, sensors),
        "measurements": 0,
    }
    conn.commit()
    for done, sensor in enumerate(sensors, start=1):
        results = client.measurements(sensor.sensor_id, first_day, last_day)
        # PM and benzene are also sampled by hand on filters: one value a day, code ending in -24g
        hourly = [m for m in results if m.is_hourly]
        counts["measurements"] += warehouse.upsert_measurements(conn, hourly)
        conn.commit()          # per sensor: an interrupted load keeps what it already has
        if done % 25 == 0:
            log.info("GIOS: %s of %s sensors, %s results so far", done, len(sensors), counts["measurements"])
    log.info("GIOS %s to %s: %s", first_day, last_day, counts)
    return counts


def ingest_weather(conn: psycopg.Connection, coverage: Coverage, first_day: dt.date, last_day: dt.date,
                   session: requests.Session | None = None, today: dt.date | None = None) -> int:
    rows = 0
    for city in coverage.cities:
        hours = hourly_weather(city.latitude, city.longitude, first_day, last_day,
                               session=session, today=today)
        rows += warehouse.upsert_weather(conn, city.name, hours)
    conn.commit()
    log.info("Open-Meteo %s to %s: %s rows", first_day, last_day, rows)
    return rows
