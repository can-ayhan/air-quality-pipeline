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


def test_all_pages_are_read():
    stations = load("gios_stations.json")[gios.STATIONS]
    session = ScriptedSession([
        FakeResponse({gios.STATIONS: stations[:6], "totalPages": 3}),
        FakeResponse({gios.STATIONS: stations[6:12], "totalPages": 3}),
        FakeResponse({gios.STATIONS: stations[12:], "totalPages": 3}),
    ])
    assert len(GiosClient(session=session).stations()) == 14
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
