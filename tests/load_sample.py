"""Load the saved API responses into the raw schema, through the ordinary ingest code.

    python tests/load_sample.py && dbt build --project-dir dbt --profiles-dir dbt

One day (20 April 2026) of two sensors in Warsaw and the weather of that day:
enough to build and test every model without calling the APIs. CI uses it.
"""

from __future__ import annotations

import datetime as dt

from airquality import ingest, warehouse
from airquality.config import City, Coverage, load_coverage
from airquality.gios import GiosClient
from fixture_api import FixtureSession

DAY = dt.date(2026, 4, 20)


def sample_coverage() -> Coverage:
    warsaw = next(city for city in load_coverage().cities if city.name == "Warszawa")
    return Coverage([City(warsaw.name, warsaw.latitude, warsaw.longitude)], load_coverage().pollutants)


def load(conn) -> dict[str, int]:
    session = FixtureSession()
    coverage = sample_coverage()
    counts = ingest.ingest_air_quality(conn, GiosClient(session=session, pause=0), coverage, DAY, DAY)
    counts["weather_hours"] = ingest.ingest_weather(conn, coverage, DAY, DAY, session=session,
                                                    today=DAY + dt.timedelta(days=1))
    return counts


if __name__ == "__main__":
    with warehouse.connect() as connection:
        warehouse.ensure_raw_schema(connection)
        print(load(connection))
