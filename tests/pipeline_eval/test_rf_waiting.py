import pytest

from tools.pipeline_eval.variants.rf_waiting import replace_waiter, simulate


def test_single_slot_uses_started_rf_and_keeps_fifo_on_exact_ties():
    visits = [(0, 1, 10), (2, 1, 10), (3, 2, 10), (4, 3, 10), (5, None, 0)]
    assert simulate(visits, 1, "fifo") == [(0, 0, 10), (1, 10, 20)]
    assert simulate(visits, 1, "latest") == [(0, 0, 10), (3, 10, 20)]
    assert simulate(visits, 1, "oldest_rf") == [(0, 0, 10), (2, 10, 20)]
    assert not replace_waiter("oldest_rf", 2, 3, {2: 5, 3: 5})


def test_completed_work_promotes_waiter_before_an_arrival_at_the_same_instant():
    visits = [(0, 1, 10), (1, 2, 9), (3, 1, 20), (10, 2, 30), (10, None, 0)]
    assert simulate(visits, 2, "latest") == [
        (0, 0, 10),
        (1, 1, 10),
        (2, 10, 30),
        (3, 10, 40),
    ]
    assert simulate([(0, None, 0)], 2, "fifo") == []


def test_invalid_trace_or_configuration_is_rejected():
    with pytest.raises(ValueError):
        simulate([(1, 1, 1), (0, 2, 1)], 1, "fifo")
    with pytest.raises(ValueError):
        simulate([(0, 2, 0)], 1, "fifo")
    with pytest.raises(ValueError):
        simulate([], 0, "fifo")
    with pytest.raises(ValueError):
        simulate([], 1, "anything")
