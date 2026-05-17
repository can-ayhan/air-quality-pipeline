import datetime as dt

import pytest

from airquality import gios, ingest
from airquality.config import City, Coverage
from airquality.gios import GiosClient
from fixture_api import FixtureSession

DAY = dt.date(2026, 4, 20)
WARSAW = Coverage([City("Warszawa", 52.2297, 21.0122)], ["PM10", "PM2.5", "NO2", "O3", "SO2", "CO", "C6H6"])


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(gios.time, "sleep", lambda seconds: None)


def count(conn, table: str) -> int:
    return conn.execute(f"select count(*) from raw.{table}").fetchone()[0]


def test_only_covered_cities_and_pollutants_are_loaded(conn):
    counts = ingest.ingest_air_quality(conn, GiosClient(session=FixtureSession()), WARSAW, DAY, DAY)
    assert counts == {"stations": 10, "sensors": 5, "measurements": 48}
    cities = conn.execute("select distinct city from raw.gios_station").fetchall()
    assert cities == [("Warszawa",)]
    codes = {row[0] for row in conn.execute("select pollutant_code from raw.gios_sensor")}
    assert codes == {"C6H6", "CO", "NO2", "PM10", "PM2.5"}       # station 530 also measures NO and NOx


def test_loading_the_same_day_twice_changes_nothing(conn):
    client = GiosClient(session=FixtureSession())
    ingest.ingest_air_quality(conn, client, WARSAW, DAY, DAY)
    before = conn.execute("select sum(value), count(*) from raw.gios_measurement").fetchone()
    ingest.ingest_air_quality(conn, client, WARSAW, DAY, DAY)
    after = conn.execute("select sum(value), count(*) from raw.gios_measurement").fetchone()
    assert before == after == (pytest.approx(847.3), 48)


def test_a_corrected_value_replaces_the_old_one(conn):
    client = GiosClient(session=FixtureSession())
    ingest.ingest_air_quality(conn, client, WARSAW, DAY, DAY)
    conn.execute("update raw.gios_measurement set value = -1 where sensor_id = 3584")
    ingest.ingest_air_quality(conn, client, WARSAW, DAY, DAY)
    lowest = conn.execute("select min(value) from raw.gios_measurement where sensor_id = 3584").fetchone()[0]
    assert lowest > 0


def test_weather_is_loaded_per_city_and_is_repeatable(conn):
    for _ in range(2):
        rows = ingest.ingest_weather(conn, WARSAW, DAY, DAY, session=FixtureSession(),
                                     today=dt.date(2026, 4, 21))
        assert rows == 24
    assert count(conn, "openmeteo_hourly") == 24
    row = conn.execute(
        """select temperature_c, wind_speed_ms from raw.openmeteo_hourly
           where city = 'Warszawa' order by time_utc limit 1"""
    ).fetchone()
    assert row == (10.6, 3.91)
