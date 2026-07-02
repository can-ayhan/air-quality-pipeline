"""Writes to the raw schema. Every write is an upsert on the table's key."""

from __future__ import annotations

import psycopg

from airquality.config import RAW_SCHEMA_FILE, warehouse_conninfo
from airquality.gios import Measurement, Sensor, Station
from airquality.openmeteo import WeatherHour


def connect() -> psycopg.Connection:
    return psycopg.connect(warehouse_conninfo())


def ensure_raw_schema(conn: psycopg.Connection) -> None:
    conn.execute(RAW_SCHEMA_FILE.read_text(encoding="utf-8"))
    conn.commit()


def upsert_stations(conn: psycopg.Connection, stations: list[Station]) -> int:
    with conn.cursor() as cur:
        cur.executemany(
            """insert into raw.gios_station
                   (station_id, code, name, city, voivodeship, street, latitude, longitude)
               values (%s, %s, %s, %s, %s, %s, %s, %s)
               on conflict (station_id) do update set
                   code = excluded.code, name = excluded.name, city = excluded.city,
                   voivodeship = excluded.voivodeship, street = excluded.street,
                   latitude = excluded.latitude, longitude = excluded.longitude, loaded_at = now()""",
            [(s.station_id, s.code, s.name, s.city, s.voivodeship, s.street, s.latitude, s.longitude)
             for s in stations],
        )
    return len(stations)


def upsert_sensors(conn: psycopg.Connection, sensors: list[Sensor]) -> int:
    with conn.cursor() as cur:
        cur.executemany(
            """insert into raw.gios_sensor (sensor_id, station_id, pollutant_code, pollutant_name)
               values (%s, %s, %s, %s)
               on conflict (sensor_id) do update set
                   station_id = excluded.station_id, pollutant_code = excluded.pollutant_code,
                   pollutant_name = excluded.pollutant_name, loaded_at = now()""",
            [(s.sensor_id, s.station_id, s.pollutant_code, s.pollutant_name) for s in sensors],
        )
    return len(sensors)


def upsert_measurements(conn: psycopg.Connection, measurements: list[Measurement]) -> int:
    """Insert new results and update changed ones. Returns how many rows that was.

    A result that is already stored with the same value is left alone, loaded_at
    included, so loaded_at says when a row last changed. The incremental model
    downstream relies on that to pick up only what is new.
    """
    if not measurements:
        return 0
    with conn.cursor() as cur:
        cur.executemany(
            """insert into raw.gios_measurement as stored (sensor_id, sensor_code, measured_at_cet, value)
               values (%s, %s, %s, %s)
               on conflict (sensor_id, measured_at_cet) do update set
                   sensor_code = excluded.sensor_code, value = excluded.value, loaded_at = now()
               where stored.value is distinct from excluded.value
                  or stored.sensor_code is distinct from excluded.sensor_code""",
            [(m.sensor_id, m.sensor_code, m.measured_at_cet, m.value) for m in measurements],
        )
        return cur.rowcount


def upsert_weather(conn: psycopg.Connection, city: str, hours: list[WeatherHour]) -> int:
    with conn.cursor() as cur:
        cur.executemany(
            """insert into raw.openmeteo_hourly
                   (city, time_utc, temperature_c, relative_humidity_pct, wind_speed_ms,
                    wind_direction_deg, precipitation_mm, surface_pressure_hpa)
               values (%s, %s, %s, %s, %s, %s, %s, %s)
               on conflict (city, time_utc) do update set
                   temperature_c = excluded.temperature_c,
                   relative_humidity_pct = excluded.relative_humidity_pct,
                   wind_speed_ms = excluded.wind_speed_ms,
                   wind_direction_deg = excluded.wind_direction_deg,
                   precipitation_mm = excluded.precipitation_mm,
                   surface_pressure_hpa = excluded.surface_pressure_hpa,
                   loaded_at = now()""",
            [(city, h.time_utc, h.temperature_c, h.relative_humidity_pct, h.wind_speed_ms,
              h.wind_direction_deg, h.precipitation_mm, h.surface_pressure_hpa) for h in hours],
        )
    return len(hours)
