"""Which day a DAG run is for. Kept free of Airflow imports so it can be tested without it."""

from __future__ import annotations

from datetime import date, timedelta


def target_day(dag_run, params) -> str:
    """The day a run loads, as YYYY-MM-DD.

    A date given when the run is triggered by hand wins. Otherwise it is the day
    the data interval starts on. For a scheduled run and for a backfill that is
    the run's own day; for a run triggered by hand Airflow fills in the latest
    finished interval, which is the day the last scheduled run loaded. A run
    without an interval loads the day before it runs.
    """
    chosen = (params or {}).get("target_date")
    if chosen:
        return date.fromisoformat(str(chosen)).isoformat()
    start = getattr(dag_run, "data_interval_start", None)
    if start is not None:
        return start.strftime("%Y-%m-%d")
    return (dag_run.run_after - timedelta(days=1)).strftime("%Y-%m-%d")


def days_before(day: str, days: int) -> str:
    return (date.fromisoformat(day) - timedelta(days=days)).isoformat()
