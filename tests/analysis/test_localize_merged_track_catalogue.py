"""Cold regional pattern search and geographically meaningful error units."""

import importlib
from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def tool(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "tools"))
    return importlib.import_module("localize_merged_track_catalogue")


def test_fixed_grid_then_refinement_without_reference_coordinate(tool):
    target = np.array([-37.0, 48.0])
    calls = []

    def objective(point):
        calls.append(point.copy())
        return np.sum((point - target) ** 2)

    result = tool.pattern_search(objective)
    assert len(calls) == result["evaluations"] <= 65
    assert all(np.linalg.norm(p) <= 250 for p in calls)
    assert np.linalg.norm(np.array(result["east_north_km"]) - target) < 0.5
    assert len({tuple(p) for p in calls}) == len(calls)


def test_position_error_is_kilometres_and_not_frequency_score(tool):
    assert tool.distance_km((37.0, -122.0), (37.0, -122.0)) == 0
    assert tool.distance_km((0.0, 0.0), (0.0, 1.0)) == pytest.approx(111.195, rel=1e-4)


def test_discovery_subset_uses_real_points_and_keeps_original_data(tool):
    times = np.linspace(0.0, 100.0, 101)
    original = dict(times=times, values=2 * times, observation_ids=[str(i) for i in range(101)])
    subset = tool.discovery_subset([("a", [original])])[0][1][0]
    assert len(subset["times"]) == 8
    assert subset["times"][0] == 0 and subset["times"][-1] == 100
    assert set(subset["observation_ids"]) <= set(original["observation_ids"])
    np.testing.assert_array_equal(subset["values"], 2 * subset["times"])
    assert len(original["values"]) == 101
    assert not tool.raw_curvature(original)
