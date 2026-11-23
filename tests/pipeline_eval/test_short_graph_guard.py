from pathlib import Path
import runpy

import pytest


GUARD = runpy.run_path(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3/short_graph_guard.py"))
lane_counts = GUARD["lane_counts"]


def row(radio=1, channel=3, rf=10_900_000_000.0):
    return {"receiver": radio, "channel": channel, "actual_rf_hz": rf}


def test_small_lanes_remain_separate_at_all_three_original_boundaries():
    rows = [row()] * 7 + [row(radio=2)] * 7 + [row(channel=4)] * 7 + [row(rf=10_900_000_001.0)] * 7
    bound = lane_counts(rows, 8)
    assert bound["proven"] and bound["winning_rows"] == 28
    assert len(bound["lanes"]) == 4 and all(lane["rows"] == 7 for lane in bound["lanes"])


def test_one_lane_at_the_exact_minimum_requires_the_full_graph():
    bound = lane_counts([row()] * 8 + [row(radio=2)], 8)
    assert not bound["proven"]
    assert bound["minimum_points"] == 8


def test_configuration_is_integer_and_validated():
    with pytest.raises(ValueError, match="minimum point count"):
        lane_counts([row()], 8.0)
