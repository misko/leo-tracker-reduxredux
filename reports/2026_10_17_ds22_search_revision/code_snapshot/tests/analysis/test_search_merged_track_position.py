"""A narrow correct basin must survive a better-looking coarse false basin."""

import importlib
from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def tool(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "tools"))
    return importlib.import_module("search_merged_track_position")


def test_regional_coverage_finds_narrow_basin_and_preserves_alternatives(tool):
    target = np.array([-37.0, 48.0])
    false = np.array([100.0, 0.0])
    calls = []

    def objective(point):
        calls.append(point.copy())
        return min(np.sum((point - target) ** 2) / 100, 10 + np.sum((point - false) ** 2) / 10000)

    result = tool.regional_search(objective)
    assert result["coarse_evaluations"] == 81
    assert len(result["basins"]) == 3
    assert np.linalg.norm(np.array(result["east_north_km"]) - target) < 0.2
    assert result["evaluations"] == len(calls) <= 250
    assert len({tuple(p) for p in calls}) == len(calls)
    assert all(np.linalg.norm(p) <= 250 + 1e-9 for p in calls)
    assert any(np.linalg.norm(np.array(r["start"]) - false) < 1 for r in result["basins"])


def test_insufficient_global_budget_is_explicit(tool):
    with pytest.raises(ValueError, match="budget"):
        tool.regional_search(lambda p: float(p @ p), budget=50)
