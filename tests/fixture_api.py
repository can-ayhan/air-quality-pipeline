"""Stand-in for requests.Session that answers from the saved API responses in tests/fixtures."""

from __future__ import annotations

import json
import re
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class FakeResponse:
    def __init__(self, body: dict | None = None, status_code: int = 200, headers: dict | None = None):
        self._body = body or {}
        self.status_code = status_code
        self.headers = headers or {}

    def json(self) -> dict:
        return self._body

    @property
    def text(self) -> str:
        return json.dumps(self._body, ensure_ascii=False)


class FixtureSession:
    """Serves the station list, the sensors of station 530, one day of two sensors and one day of weather.

    Anything else that is asked for gets an empty, well-formed answer, the way the
    API answers for a station without sensors or a sensor without results.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def get(self, url: str, params: dict | None = None, timeout: float | None = None) -> FakeResponse:
        params = dict(params or {})
        self.calls.append((url, params))
        if "open-meteo.com" in url:
            return FakeResponse(load("openmeteo_warszawa_2026-04-20.json"))
        if url.endswith("/station/findAll"):
            return FakeResponse(load("gios_stations.json"))
        if match := re.search(r"/station/sensors/(\d+)$", url):
            return self._file_or_empty(f"gios_sensors_{match.group(1)}.json",
                                       "Lista stanowisk pomiarowych dla podanej stacji")
        if match := re.search(r"/archivalData/getDataBySensor/(\d+)$", url):
            day = params.get("dateFrom", "")[:10]
            return self._file_or_empty(f"gios_measurements_{match.group(1)}_{day}.json",
                                       "Lista archiwalnych wyników pomiarów")
        return FakeResponse({"error": "not found"}, status_code=404)

    @staticmethod
    def _file_or_empty(name: str, key: str) -> FakeResponse:
        if (FIXTURES / name).exists():
            return FakeResponse(load(name))
        return FakeResponse({key: [], "totalPages": 1})


class ScriptedSession:
    """Returns the given responses in order, whatever is asked."""

    def __init__(self, responses: list) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, dict]] = []

    def get(self, url: str, params: dict | None = None, timeout: float | None = None) -> FakeResponse:
        self.calls.append((url, dict(params or {})))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response
