"""Daily load of air quality and weather, then the dbt build.

    ingest_air_quality ──┐
                         ├──> dbt_build
    ingest_weather ──────┘

A run belongs to one day: the day its data interval starts on. The run that
starts at 06:00 UTC on the 2nd loads the 1st. A backfill creates one run per
day of its range. A run triggered by hand loads the day of the last scheduled
run, or the day given as target_date.

Each run also asks again for the two days before its own. Results that were
missing in the morning are sometimes published later, a request covers a range
of days at no extra cost, and rows that have not changed are left alone.

The ingests call free public APIs that are sometimes slow or briefly down, so
they are retried with a growing pause. The dbt build is not: a failed test
fails again on the same data, and should be looked at instead.

A task that fails for good sends one message to the webhook in ALERT_WEBHOOK_URL.
"""

from __future__ import annotations

import os
from datetime import timedelta

import pendulum
from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG, Param
from airflow.timetables.interval import CronDataIntervalTimetable

from alerts import notify_failure
from run_day import days_before, target_day

PIPELINE_HOME = os.environ.get("PIPELINE_HOME", "/opt/pipeline")
PIPELINE_VENV = os.environ.get("PIPELINE_VENV", "/opt/pipeline-venv")
INGEST = f"{PIPELINE_VENV}/bin/python -m airquality ingest"
DBT = f"{PIPELINE_VENV}/bin/dbt --no-use-colors"
DBT_DIRS = f"--project-dir {PIPELINE_HOME}/dbt --profiles-dir {PIPELINE_HOME}/dbt"

RELOAD_DAYS = 2
DAY = "{{ target_day(dag_run, params) }}"
FIRST_DAY = f"{{{{ days_before(target_day(dag_run, params), {RELOAD_DAYS}) }}}}"

default_args = {
    "retries": 3,
    "retry_delay": timedelta(minutes=2),
    "retry_exponential_backoff": 2.0,             # the pause doubles each time, plus jitter
    "max_retry_delay": timedelta(minutes=30),
    "execution_timeout": timedelta(minutes=45),   # a cold archive endpoint needs minutes, not hours
    "do_xcom_push": False,
    "on_failure_callback": notify_failure,
    # one instance of a task at a time across runs: a backfill must not multiply the
    # requests to the APIs or run two dbt builds on the same tables
    "max_active_tis_per_dag": 1,
}

with DAG(
    dag_id="air_quality_daily",
    description="GIOS air quality and Open-Meteo weather into the warehouse, then dbt build",
    schedule=CronDataIntervalTimetable("0 6 * * *", timezone="UTC"),
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    default_args=default_args,
    params={
        "target_date": Param(
            None,
            type=["null", "string"],
            format="date",
            title="Day to load",
            description="YYYY-MM-DD. Leave empty to load the day of the last scheduled run.",
        ),
    },
    user_defined_macros={"target_day": target_day, "days_before": days_before},
    tags=["air-quality"],
    doc_md=__doc__,
) as dag:
    ingest_air_quality = BashOperator(
        task_id="ingest_air_quality",
        bash_command=f"{INGEST} --source air --from {FIRST_DAY} --to {DAY}",
    )

    ingest_weather = BashOperator(
        task_id="ingest_weather",
        bash_command=f"{INGEST} --source weather --from {FIRST_DAY} --to {DAY}",
    )

    dbt_build = BashOperator(
        task_id="dbt_build",
        bash_command=f"{DBT} build {DBT_DIRS}",
        retries=0,
        execution_timeout=timedelta(minutes=20),
    )

    [ingest_air_quality, ingest_weather] >> dbt_build
