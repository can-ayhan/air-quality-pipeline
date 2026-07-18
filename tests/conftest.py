"""Shared fixtures. Tests that write to PostgreSQL use their own database and skip without one.

The pipeline package is imported inside the fixtures, not at the top: the DAG
tests run in an environment that has Airflow and nothing of the pipeline.
"""

from __future__ import annotations

import os

import pytest

TEST_DB = "warehouse_test"


@pytest.fixture(scope="session")
def test_database() -> str:
    """Connection string of an empty test database on the configured server."""
    import psycopg

    from airquality.config import warehouse_conninfo

    try:
        admin = psycopg.connect(warehouse_conninfo(), autocommit=True, connect_timeout=3)
    except psycopg.OperationalError as exc:
        pytest.skip(f"no PostgreSQL to test against: {exc}")
    with admin:
        admin.execute(f"drop database if exists {TEST_DB} with (force)")
        admin.execute(f"create database {TEST_DB}")
    os.environ["WAREHOUSE_DB"] = TEST_DB
    return warehouse_conninfo()


@pytest.fixture
def conn(test_database):
    import psycopg

    from airquality import warehouse

    with psycopg.connect(test_database) as connection:
        connection.execute("drop schema if exists raw cascade")
        warehouse.ensure_raw_schema(connection)
        yield connection
