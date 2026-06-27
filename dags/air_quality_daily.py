"""Daily load of air quality and weather, then the dbt build.

    ingest_air_quality ──┐
                         ├──> dbt_build
    ingest_weather ──────┘

A run belongs to one day: the day its data interval starts on. The run that
starts at 06:00 UTC on the 2nd loads the 1st.
"""

from __future__ import annotations

import os

import pendulum
from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG
from airflow.timetables.interval import CronDataIntervalTimetable

PIPELINE_HOME = os.environ.get("PIPELINE_HOME", "/opt/pipeline")
PIPELINE_VENV = os.environ.get("PIPELINE_VENV", "/opt/pipeline-venv")
INGEST = f"{PIPELINE_VENV}/bin/python -m airquality ingest"
DBT = f"{PIPELINE_VENV}/bin/dbt"
DBT_DIRS = f"--project-dir {PIPELINE_HOME}/dbt --profiles-dir {PIPELINE_HOME}/dbt"

DAY = "{{ data_interval_start | ds }}"

with DAG(
    dag_id="air_quality_daily",
    description="GIOS air quality and Open-Meteo weather into the warehouse, then dbt build",
    schedule=CronDataIntervalTimetable("0 6 * * *", timezone="UTC"),
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    tags=["air-quality"],
    doc_md=__doc__,
) as dag:
    ingest_air_quality = BashOperator(
        task_id="ingest_air_quality",
        bash_command=f"{INGEST} --source air --from {DAY} --to {DAY}",
    )

    ingest_weather = BashOperator(
        task_id="ingest_weather",
        bash_command=f"{INGEST} --source weather --from {DAY} --to {DAY}",
    )

    dbt_build = BashOperator(
        task_id="dbt_build",
        bash_command=f"{DBT} build {DBT_DIRS}",
    )

    [ingest_air_quality, ingest_weather] >> dbt_build
