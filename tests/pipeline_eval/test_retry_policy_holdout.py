import pytest

from tools.pipeline_eval.qualification import retry_policy_holdout_results as results
from tools.pipeline_eval.variants.retry_policy_holdout import TwoFailureCadence


def test_timer_waits_only_after_two_executed_misses_and_at_exact_boundary():
    timer = TwoFailureCadence()
    key = (0, 10)
    timer.observed(key, 10, False)
    assert timer.allows(key, 20)
    timer.observed(key, 20, False)
    assert not timer.allows(key, 800_000_019)
    with pytest.raises(ValueError, match="skipped retry"):
        timer.observed(key, 30, False)
    assert timer.allows(key, 800_000_020)
    assert timer.allows((1, 10), 30)
    timer.observed(key, 800_000_020, True)
    timer.observed(key, 800_000_021, False)
    assert timer.allows(key, 800_000_022)


def test_success_resets_streak_and_late_executed_failure_restarts_wait():
    timer = TwoFailureCadence()
    key = (0, 10)
    for time, hit in ((10, False), (20, True), (30, False), (40, False), (900_000_000, False)):
        timer.observed(key, time, hit)
    assert not timer.allows(key, 1_699_999_999)
    assert timer.allows(key, 1_700_000_000)


def test_physical_key_count_control_and_no_future_outcome_updates():
    left, right = (0, 10), (1, 10)
    events = [
        (1, left, 0, False),
        (2, left, 200_000_000, False),
        (3, right, 250_000_000, False),
        (4, left, 500_000_000, True),
        (5, right, 700_000_000, True),
        (6, left, 1_050_000_000, False),
    ]
    plan = results.schedules(events, "recording")
    assert plan[results.FULL] == set(range(1, 7))
    assert plan[results.PRIMARY] == set()
    assert plan[results.MISS] == {1, 3}
    assert plan[results.TWO] == {1, 2, 3, 5, 6}
    assert results.schedules(events, "recording") == plan
    for key in (left, right):
        ids = {v for v, k, _, _ in events if k == key}
        assert len(ids & plan[results.CONTROL]) == len(ids & plan[results.TWO])
