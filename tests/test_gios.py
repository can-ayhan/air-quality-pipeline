import datetime as dt

import pytest
import requests

from airquality import gios
from airquality.gios import GiosClient, GiosError
from fixture_api import FakeResponse, FixtureSession, ScriptedSession, load


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(gios.time, "sleep", lambda seconds: None)


def test_stations_are_parsed_from_the_polish_keys():
    stations = GiosClient(session=FixtureSession()).stations()
    assert len(stations) == 14
    station = next(s for s in stations if s.station_id == 530)
    assert station.code == "MzWarAlNiepo"
    assert station.name == "Warszawa, Al. Niepodległości"
    assert station.city == "Warszawa"
    assert station.voivodeship == "MAZOWIECKIE"
    assert station.latitude == pytest.approx(52.219, abs=0.01)
    assert station.longitude == pytest.approx(21.004, abs=0.01)


def test_sensors_of_a_station():
    sensors = GiosClient(session=FixtureSession()).sensors(530)
    assert {s.pollutant_code for s in sensors} == {"C6H6", "CO", "NO", "NO2", "NOx", "PM10", "PM2.5"}
    pm10 = next(s for s in sensors if s.pollutant_code == "PM10")
    assert (pm10.sensor_id, pm10.station_id) == (3584, 530)


def test_measurements_keep_the_published_clock():
    session = FixtureSession()
    results = GiosClient(session=session).measurements(3584, dt.date(2026, 4, 20), dt.date(2026, 4, 20))
    assert len(results) == 24
    assert results[0].measured_at_cet == dt.datetime(2026, 4, 20, 0, 0)
    assert results[-1].measured_at_cet == dt.datetime(2026, 4, 20, 23, 0)
    assert results[0].value == 15.0
    assert all(r.sensor_code == "MzWarAlNiepo-PM10-1g" and r.is_hourly for r in results)
    url, params = session.calls[0]
    assert url.endswith("/archivalData/getDataBySensor/3584")
    assert (params["dateFrom"], params["dateTo"]) == ("2026-04-20 00:00", "2026-04-20 23:00")


def test_a_missing_value_stays_missing():
    item = {"Kod stanowiska": "MzWarAlNiepo-PM10-1g", "Data": "2026-04-20 05:00:00", "Wartość": None}
    assert gios.parse_measurement(3584, item).value is None


def test_daily_manual_results_are_not_hourly():
    item = {"Kod stanowiska": "MzWarAlNiepo-PM10-24g", "Data": "2026-04-20 00:00:00", "Wartość": 21.3}
    assert not gios.parse_measurement(1, item).is_hourly


def test_all_pages_are_read():
    rows = load("gios_measurements_3584_2026-04-20.json")[gios.MEASUREMENTS]
    session = ScriptedSession([
        FakeResponse({gios.MEASUREMENTS: rows[:10], "totalPages": 3}),
        FakeResponse({gios.MEASUREMENTS: rows[10:20], "totalPages": 3}),
        FakeResponse({gios.MEASUREMENTS: rows[20:], "totalPages": 3}),
    ])
    results = GiosClient(session=session).measurements(3584, dt.date(2026, 4, 20), dt.date(2026, 4, 20))
    assert len(results) == 24
    assert [params["page"] for _, params in session.calls] == [0, 1, 2]


def test_server_errors_and_timeouts_are_retried():
    session = ScriptedSession([
        FakeResponse(status_code=503),
        requests.ConnectionError("connection reset"),
        FakeResponse({gios.STATIONS: [], "totalPages": 1}),
    ])
    assert GiosClient(session=session).stations() == []
    assert len(session.calls) == 3


def test_it_gives_up_after_the_last_retry():
    session = ScriptedSession([FakeResponse(status_code=503)] * 3)
    with pytest.raises(GiosError, match="HTTP 503"):
        GiosClient(session=session, max_retries=3).stations()
    assert len(session.calls) == 3


def test_a_client_error_is_not_retried():
    session = ScriptedSession([FakeResponse({"error": "gone"}, status_code=410)])
    with pytest.raises(GiosError, match="HTTP 410"):
        GiosClient(session=session).stations()
    assert len(session.calls) == 1
