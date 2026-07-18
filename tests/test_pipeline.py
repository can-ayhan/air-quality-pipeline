"""The whole path on the saved API responses: ingest, dbt build, and a bad row that must stop the marts.

Needs dbt on the path and a PostgreSQL to build in; skipped otherwise.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import load_sample

# on the path, or next to the interpreter when the virtualenv is not activated
DBT = shutil.which("dbt") or shutil.which("dbt", path=str(Path(sys.executable).parent))
PROJECT = Path(__file__).resolve().parents[1] / "dbt"

pytestmark = pytest.mark.skipif(DBT is None, reason="dbt is not installed")


def dbt_build(*extra: str) -> subprocess.CompletedProcess:
    # WAREHOUSE_DB already points at the test database (see conftest)
    command = [DBT, "--no-use-colors", "build", "--project-dir", str(PROJECT), "--profiles-dir", str(PROJECT)]
    return subprocess.run(
        [*command, *extra],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env={**os.environ, "DBT_SEND_ANONYMOUS_USAGE_STATS": "false", "PYTHONUTF8": "1"},
    )


@pytest.fixture
def built(conn):
    """Sample data loaded and the models built on it, in an otherwise empty database."""
    for schema in ("staging", "marts", "reference"):
        conn.execute(f"drop schema if exists {schema} cascade")
    load_sample.load(conn)
    conn.commit()
    result = dbt_build()
    assert result.returncode == 0, result.stdout[-3000:]
    return conn


def test_models_build_and_every_test_passes(built):
    assert built.execute("select count(*) from marts.fct_measurement_hourly").fetchone()[0] == 48
    rows = built.execute(
        """select pollutant_code, hours_measured, is_complete_day, daily_mean, exceeds_who_guideline,
                  avg_temperature_c is not null
           from marts.mart_station_daily order by pollutant_code"""
    ).fetchall()
    assert [(r[0], r[1], r[2], float(r[3]), r[4], r[5]) for r in rows] == [
        ("NO2", 24, True, 13.96, False, True),      # 335.0 / 24, guideline 25
        ("PM10", 24, True, 21.35, False, True),     # 512.3 / 24, guideline 45
    ]


def test_a_second_build_adds_nothing(built):
    result = dbt_build()
    assert result.returncode == 0, result.stdout[-3000:]
    assert built.execute("select count(*) from marts.fct_measurement_hourly").fetchone()[0] == 48


def test_a_result_out_of_range_stops_both_marts(built):
    # carbon monoxide as the current-data endpoint publishes it: micrograms, not milligrams
    built.execute(
        """insert into raw.gios_measurement (sensor_id, sensor_code, measured_at_cet, value)
           values (3576, 'MzWarAlNiepo-CO-1g', '2026-04-20 12:00', 412.0)"""
    )
    built.commit()
    result = dbt_build()
    assert result.returncode != 0
    assert "FAIL 1 assert_values_are_plausible" in result.stdout
    assert "SKIP relation marts.fct_measurement_hourly" in result.stdout
    assert "SKIP relation marts.mart_station_daily" in result.stdout
    # the marts are as they were: the bad row did not get in
    fact = built.execute("select count(*), max(value) from marts.fct_measurement_hourly").fetchone()
    assert fact == (48, 35.5)


def test_a_reloaded_day_replaces_its_rows(built):
    built.execute(
        """update raw.gios_measurement set value = value + 10, loaded_at = now()
           where sensor_id = 3584 and measured_at_cet = '2026-04-20 05:00'"""
    )
    built.commit()
    result = dbt_build()
    assert result.returncode == 0, result.stdout[-3000:]
    count, total = built.execute(
        "select count(*), sum(value) from marts.fct_measurement_hourly where sensor_id = 3584"
    ).fetchone()
    assert (count, total) == (24, pytest.approx(522.3))
