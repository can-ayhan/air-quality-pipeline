import datetime as dt

import pytest

from airquality import gios, ingest
from airquality.config import City, Coverage
from airquality.gios import GiosClient, Measurement
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
    assert counts == {"stations": 10, "sensors": 5, "measurements": 48, "changed": 48}
    cities = conn.execute("select distinct city from raw.gios_station").fetchall()
    assert cities == [("Warszawa",)]
    codes = {row[0] for row in conn.execute("select pollutant_code from raw.gios_sensor")}
    assert codes == {"C6H6", "CO", "NO2", "PM10", "PM2.5"}       # station 530 also measures NO and NOx


def test_loading_the_same_day_twice_changes_nothing(conn):
    client = GiosClient(session=FixtureSession())
    state = "select sum(value), count(*), max(loaded_at) from raw.gios_measurement"
    ingest.ingest_air_quality(conn, client, WARSAW, DAY, DAY)
    before = conn.execute(state).fetchone()
    counts = ingest.ingest_air_quality(conn, client, WARSAW, DAY, DAY)
    assert (counts["measurements"], counts["changed"]) == (48, 0)
    assert conn.execute(state).fetchone() == before
    assert before[:2] == (pytest.approx(847.3), 48)


def test_a_corrected_value_replaces_the_old_one(conn):
    client = GiosClient(session=FixtureSession())
    ingest.ingest_air_quality(conn, client, WARSAW, DAY, DAY)
    conn.execute("""update raw.gios_measurement set value = -1, loaded_at = '2026-04-21 06:00+00'
                    where sensor_id = 3584 and measured_at_cet = '2026-04-20 05:00'""")
    counts = ingest.ingest_air_quality(conn, client, WARSAW, DAY, DAY)
    assert counts["changed"] == 1
    value, reloaded = conn.execute(
        """select value, loaded_at > '2026-04-21 06:00+00' from raw.gios_measurement
           where sensor_id = 3584 and measured_at_cet = '2026-04-20 05:00'"""
    ).fetchone()
    assert value > 0 and reloaded


def test_daily_manual_samples_are_left_out(conn, monkeypatch):
    def with_a_daily_sample(self, sensor_id, first_day, last_day):
        stamp = dt.datetime(2026, 4, 20)
        return [
            Measurement(sensor_id, "MzWarAlNiepo-PM10-1g", stamp, 15.0),
            Measurement(sensor_id, "MzWarAlNiepo-PM10-24g", stamp, 21.3),
        ]

    monkeypatch.setattr(GiosClient, "measurements", with_a_daily_sample)
    counts = ingest.ingest_air_quality(conn, GiosClient(session=FixtureSession()), WARSAW, DAY, DAY)
    assert (counts["measurements"], counts["changed"]) == (5, 5)
    assert conn.execute("select distinct sensor_code from raw.gios_measurement").fetchall() == [
        ("MzWarAlNiepo-PM10-1g",)
    ]


def test_an_empty_answer_for_every_sensor_is_an_error(conn):
    another_day = dt.date(2026, 4, 25)          # the saved responses only have 20 April
    with pytest.raises(ingest.NoDataError, match="no hourly results from 5 sensors for 2026-04-25"):
        ingest.ingest_air_quality(conn, GiosClient(session=FixtureSession()), WARSAW,
                                  another_day, another_day)
    assert count(conn, "gios_station") == 10    # the station list is still worth keeping


def test_results_for_earlier_days_only_are_an_error_too(conn):
    # asked for the 20th and the 21st, the saved responses stop at the 20th
    with pytest.raises(ingest.NoDataError, match=r"for 2026-04-21 \(newest result: 2026-04-20 23:00:00\)"):
        ingest.ingest_air_quality(conn, GiosClient(session=FixtureSession()), WARSAW,
                                  DAY, DAY + dt.timedelta(days=1))
    assert count(conn, "gios_measurement") == 48    # what did arrive is kept


def test_weather_is_asked_from_the_day_before(conn):
    session = FixtureSession()
    ingest.ingest_weather(conn, WARSAW, DAY, DAY, session=session, today=dt.date(2026, 4, 21))
    _, params = session.calls[0]
    assert (params["start_date"], params["end_date"]) == ("2026-04-19", "2026-04-20")


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
