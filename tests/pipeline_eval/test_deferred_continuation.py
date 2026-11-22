from random import Random

import pytest

from tools.pipeline_eval.variants.carrier_continuation import Continuation
from tools.pipeline_eval.variants.experimental.deferred_continuation import DeferredContinuation


def factor(freq, rank=0, margin=.2):
    return dict(fractional_tracking_cfo_hz=freq, candidate_rank=rank, fractional_margin=margin)


def compare(rows, capacity):
    original = Continuation()
    proposed = DeferredContinuation(capacity)
    called = set()
    selected = []
    for i, (counter, lane, channel, values) in enumerate(rows):
        probe = dict(valid_start_counter=counter, receiver_id=lane, channel=channel, actual_rf_hz=channel * 1000)
        def measure(i=i, values=values):
            assert i not in called
            called.add(i)
            return values
        _, index, _ = original.select(dict(probe, candidates=values))
        result = proposed.select(probe, measure)
        assert result == ([] if index is None else [values[index]])
        selected.append(result)
    return proposed, called, selected


@pytest.mark.parametrize("capacity", [0, 1, 16, 128])
def test_all_histories_and_duplicate_hardware_times_across_antennas(capacity):
    rng = Random(615)
    rows = []
    now = 0
    for visit in range(800):
        now += rng.choice((1_000_000, 4_000_000, 7_000_000, 80_000_000, 80_000_001))
        channel = rng.choice((1, 3, 8))
        for lane in (0, 1):
            values = [factor(100_000 + (now % 800), rank, rng.choice((.1, .8)))
                      for rank in range(rng.choice((0, 0, 1, 2)))]
            rows.append((now, lane, channel, values))
    planner, called, _ = compare(rows, capacity)
    assert planner.counts["peak_pending_lanes"] <= capacity
    if capacity:
        assert len(called) < len(rows)


def test_empty_lanes_weak_second_candidate_age_limit_and_history_eviction():
    quiet = [(i * 4_000_000, 0, 3, []) for i in range(40)]
    _, called, _ = compare(quiet, 16)
    assert len(called) < len(quiet)
    signals = [(i * 4_000_000, 0, 3, [factor(4500)]) for i in range(8)]
    signals.append((32_000_000, 0, 3, [factor(-90_000, margin=.9), factor(4500, 1)]))
    signals.extend((i * 4_000_000, 0, 3, []) for i in range(9, 29))
    signals.append((200_000_000, 0, 3, [factor(4500)]))
    _, _, selected = compare(signals, 16)
    assert selected[8] == [factor(4500, 1)]
    assert selected[-1] == []


def test_dense_mixed_carriers_rejected_donors_and_ties():
    rng = Random(12011)
    cases = []
    for i in range(1100):
        now = i * 2_000_000
        values = []
        for rank in range(rng.choice((0, 0, 1, 1, 2, 2))):
            base = rng.choice((-32_000, -120_000, 200_000)) + (i % 200) * 120
            values.append(factor(base + rng.choice((-800, 0, 800)), rank, .25))
        cases.append((now, 0, 4, values))
    method, _, _ = compare(cases, 16)
    assert method.counts["ruled_out_by_frequency"] > 0
