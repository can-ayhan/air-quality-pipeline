"""The DAG as Airflow sees it. Needs Airflow, which is only installed in its own CI job and in the image."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

pytest.importorskip("airflow", reason="Airflow is not installed")

import air_quality_daily  # noqa: E402
from alerts import notify_failure  # noqa: E402

dag = air_quality_daily.dag


def test_dbt_build_waits_for_both_ingests():
    assert set(dag.task_ids) == {"ingest_air_quality", "ingest_weather", "dbt_build"}
    assert dag.get_task("dbt_build").upstream_task_ids == {"ingest_air_quality", "ingest_weather"}


def test_it_runs_daily_and_does_not_catch_up_on_its_own():
    assert dag.catchup is False
    assert dag.max_active_runs == 1
    assert "0 6 * * *" in dag.timetable.summary


@pytest.mark.parametrize("task_id", ["ingest_air_quality", "ingest_weather"])
def test_api_calls_are_retried_with_backoff(task_id):
    task = dag.get_task(task_id)
    assert task.retries == 3
    assert task.retry_delay == timedelta(minutes=2)
    assert task.retry_exponential_backoff == 2.0


def test_a_failed_dbt_build_is_not_retried():
    assert dag.get_task("dbt_build").retries == 0


def test_every_task_alerts_and_runs_one_at_a_time():
    for task in dag.tasks:
        callbacks = task.on_failure_callback
        assert notify_failure in (callbacks if isinstance(callbacks, list | tuple) else [callbacks])
        assert task.max_active_tis_per_dag == 1
        assert task.execution_timeout is not None


def render(task_id: str, dag_run, params) -> str:
    template = dag.get_template_env().from_string(dag.get_task(task_id).bash_command)
    return template.render(dag_run=dag_run, params=params)


def test_a_scheduled_run_loads_its_day_and_the_two_before():
    scheduled = SimpleNamespace(data_interval_start=datetime(2026, 7, 1, 6, tzinfo=UTC),
                                run_after=datetime(2026, 7, 2, 6, tzinfo=UTC))
    command = render("ingest_air_quality", scheduled, {"target_date": None})
    assert command.endswith("ingest --source air --from 2026-06-29 --to 2026-07-01")


def test_a_chosen_day_overrides_the_interval():
    manual = SimpleNamespace(data_interval_start=datetime(2026, 7, 1, 6, tzinfo=UTC),
                             run_after=datetime(2026, 7, 2, 9, tzinfo=UTC))
    command = render("ingest_weather", manual, {"target_date": "2026-03-14"})
    assert command.endswith("ingest --source weather --from 2026-03-12 --to 2026-03-14")
