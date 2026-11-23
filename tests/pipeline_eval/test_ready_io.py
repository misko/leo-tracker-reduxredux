import pytest

from reports.ALGO08.v3.ready_io import intersection


def read(start, end):
    return dict(start_ns=start, end_ns=end)


def work(start, end, cpu, before=None, after=None):
    return dict(start_ns=start, end_ns=end, cpu_ns=cpu, before=before, after=after)


def test_partial_intersection_bounds_cpu_without_assuming_when_it_ran():
    reads = [read(5, 12), read(18, 22)]
    assert intersection([work(0, 10, 8), work(15, 25, 3)], reads) == dict(
        pending_read_cpu_lower_ns=3, pending_read_cpu_upper_ns=8,
        d_state_bracket_cpu_ns=0, state_samples=0, d_state_samples=0,
    )


def test_d_state_requires_both_samples_of_same_call_and_does_not_add_to_bound():
    blocked = dict(call=0, state="D")
    other = dict(call=1, state="D")
    runnable = dict(call=0, state="R")
    assert intersection([
        work(0, 4, 3, blocked, blocked), work(4, 6, 1, blocked, other),
        work(6, 10, 2, runnable, blocked),
    ], [read(0, 10)]) == dict(
        pending_read_cpu_lower_ns=6, pending_read_cpu_upper_ns=6,
        d_state_bracket_cpu_ns=3, state_samples=6, d_state_samples=5,
    )


def test_rejects_double_counted_pending_wait_or_impossible_cpu_clock():
    with pytest.raises(ValueError, match="Invalid"):
        intersection([work(0, 10, 8)], [read(0, 6), read(2, 9)])
    with pytest.raises(ValueError, match="Invalid"):
        intersection([work(0, 10, 11)], [])
