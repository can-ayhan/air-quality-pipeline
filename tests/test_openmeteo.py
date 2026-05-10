import datetime as dt

import pytest

from airquality import openmeteo
from airquality.openmeteo import ARCHIVE_URL, FORECAST_URL, OpenMeteoError
from fixture_api import FakeResponse, FixtureSession, ScriptedSession, load


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(openmeteo.time, "sleep", lambda seconds: None)


def test_hourly_columns_become_rows():
    hours = openmeteo.parse_hourly(load("openmeteo_warszawa_2026-04-20.json"))
    assert len(hours) == 24
    first = hours[0]
    assert first.time_utc == dt.datetime(2026, 4, 20, 0, 0)
    assert first.temperature_c == 10.6
    assert first.relative_humidity_pct == 60
    assert first.wind_speed_ms == 3.91
    assert first.surface_pressure_hpa == 999.2


def test_a_variable_missing_from_the_answer_becomes_nulls():
    body = {"hourly": {"time": ["2026-04-20T00:00", "2026-04-20T01:00"], "temperature_2m": [1.0, 2.0]}}
    hours = openmeteo.parse_hourly(body)
    assert [h.temperature_c for h in hours] == [1.0, 2.0]
    assert all(h.precipitation_mm is None for h in hours)


def test_an_empty_answer_gives_no_rows():
    assert openmeteo.parse_hourly({}) == []


@pytest.mark.parametrize(("first_day", "expected"), [
    (dt.date(2026, 5, 9), FORECAST_URL),       # yesterday
    (dt.date(2026, 2, 19), FORECAST_URL),      # 80 days back: still the recent endpoint
    (dt.date(2026, 2, 18), ARCHIVE_URL),
    (dt.date(2025, 1, 1), ARCHIVE_URL),
])
def test_old_dates_go_to_the_archive(first_day, expected):
    assert openmeteo.endpoint_for(first_day, today=dt.date(2026, 5, 10)) == expected


def test_request_asks_for_utc_and_metres_per_second():
    session = FixtureSession()
    hours = openmeteo.hourly_weather(52.2297, 21.0122, dt.date(2026, 4, 20), dt.date(2026, 4, 20),
                                     session=session, today=dt.date(2026, 4, 21))
    assert len(hours) == 24
    url, params = session.calls[0]
    assert url == FORECAST_URL
    assert params["timezone"] == "UTC"
    assert params["wind_speed_unit"] == "ms"
    assert (params["start_date"], params["end_date"]) == ("2026-04-20", "2026-04-20")


def test_rate_limit_is_retried_then_reported():
    session = ScriptedSession([FakeResponse(status_code=429)] * 2)
    with pytest.raises(OpenMeteoError, match="HTTP 429"):
        openmeteo.hourly_weather(52.2, 21.0, dt.date(2026, 4, 20), dt.date(2026, 4, 20),
                                 session=session, max_retries=2)
    assert len(session.calls) == 2


def test_a_bad_request_fails_at_once():
    session = ScriptedSession([FakeResponse({"reason": "out of allowed range"}, status_code=400)])
    with pytest.raises(OpenMeteoError, match="HTTP 400"):
        openmeteo.hourly_weather(52.2, 21.0, dt.date(2026, 4, 20), dt.date(2026, 4, 20), session=session)
    assert len(session.calls) == 1
