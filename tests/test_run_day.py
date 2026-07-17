from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from run_day import days_before, target_day


def run(interval_start=None, run_after=None):
    return SimpleNamespace(data_interval_start=interval_start, run_after=run_after)


def test_a_scheduled_run_loads_the_day_its_interval_starts_on():
    # the run that starts at 06:00 on 2 July covers 1 July 06:00 to 2 July 06:00
    scheduled = run(datetime(2026, 7, 1, 6, tzinfo=UTC), datetime(2026, 7, 2, 6, tzinfo=UTC))
    assert target_day(scheduled, {"target_date": None}) == "2026-07-01"


def test_a_date_given_by_hand_wins():
    manual = run(datetime(2026, 7, 1, 6, tzinfo=UTC), datetime(2026, 7, 2, 9, 30, tzinfo=UTC))
    assert target_day(manual, {"target_date": "2026-03-14"}) == "2026-03-14"


def test_a_run_without_an_interval_loads_the_day_before_it_runs():
    assert target_day(run(run_after=datetime(2026, 7, 2, 0, 30, tzinfo=UTC)), {}) == "2026-07-01"


def test_a_date_that_is_not_a_date_is_refused():
    with pytest.raises(ValueError):
        target_day(run(), {"target_date": "yesterday"})


def test_days_before_crosses_months():
    assert days_before("2026-07-01", 2) == "2026-06-29"
    assert days_before("2026-03-01", 1) == "2026-02-28"
