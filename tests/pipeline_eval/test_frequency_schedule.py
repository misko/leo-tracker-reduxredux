from collections import Counter

import pytest

from tools.pipeline_eval.qualification.frequency_schedule_pacing import pace
from tools.pipeline_eval.variants.frequency_schedule import (
    BIN_COUNT,
    channels,
    clock_bins,
    schedules,
)


def test_nested_full_pass_lanes_and_equal_time_bin_bursts():
    ident = "fixed-case"
    clocks = [i * 30_000_000 for i in range(8000)]
    metadata = [(i, i % 8 + 1) for i in range(len(clocks)) if i % 22 != 0]
    lanes = dict(metadata)
    bins = clock_bins(clocks)
    projected = schedules(ident, metadata, clocks)
    assert len(projected["full"]) == len(metadata)
    assert set(channels(ident, 2)) < set(channels(ident, 4))
    for size in (2, 4):
        chosen = channels(ident, size)
        assert sum(channel <= 4 for channel in chosen) == size // 2
        kept, clustered = (projected[f"{name}{size}"] for name in ("lanes", "bursts"))
        assert kept == [visit for visit, lane in metadata if lane in chosen]
        assert len(kept) == len(set(clustered))
        assert Counter(bins[v] for v in kept) == Counter(bins[v] for v in clustered)
        assert {lanes[v] for v in clustered} == set(range(1, 9))
        assert min(clustered) < 400 and max(clustered) > 7600
        for time_bin in range(BIN_COUNT):
            for channel in range(1, 9):
                available = [v for v, lane in metadata if bins[v] == time_bin and lane == channel]
                local = [i for i, v in enumerate(available) if v in clustered]
                assert local == list(range(local[0], local[-1] + 1))


def test_ideal_pacing_counts_actual_releases_and_nonpreemptive_drain():
    arrivals = [0.0, 0.0, 299.5]
    costs = [200.0, 200.0, 1.0]
    one = pace(arrivals, costs, 1)
    two = pace(arrivals, costs, 2)
    assert one["completed_by_300_s"] == 1 and one["simulated_detector_ready_s"] == 401.0
    assert two["work_only_lower_bound_s"] == 200.5
    assert two["completed_by_300_s"] == 2 and two["simulated_detector_ready_s"] == 300.5
    with pytest.raises(ValueError, match="ordered"):
        pace([1.0, 0.0], [1.0, 1.0], 2)
