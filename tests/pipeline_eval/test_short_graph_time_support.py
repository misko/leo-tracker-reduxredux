from math import inf, nan, nextafter
from pathlib import Path
from runpy import run_path

import pytest


support = run_path(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3/short_graph_guard.py"))["time_support"]


def lane(times, receiver=1):
    return [dict(receiver=receiver, channel=3, actual_rf_hz=11e9, time_s=t) for t in times]


@pytest.mark.parametrize(("times", "proven"), [
    ([0, 0, 1, 2, 3, 4, 5, 6], False),
    ([0, 0, 1, 2, 3, 4, 5, nextafter(6, 0)], True),
    ([0, 1, 2, 3, 14, 15, 16, 17], True),
    ([0, 1, 2, 3, 13, 14, 15, 16], False),
    ([0] * 12, True),
])
def test_inclusive_span_and_gap_boundaries(times, proven):
    assert support(lane(reversed(times)), 8, 6., 10.)["proven"] is proven


def test_disjoint_lanes_cannot_supply_a_shared_seed():
    assert support(lane(range(7)) + lane(range(7, 14), 2), 8, 6., 10.)["proven"]


@pytest.mark.parametrize("bad", [nan, inf])
def test_invalid_times_fail_closed(bad):
    with pytest.raises(ValueError):
        support(lane([bad]), 8, 6., 10.)
