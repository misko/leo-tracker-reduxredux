from importlib import import_module
from pathlib import Path

import numpy as np
import pytest

from leo.analysis.position_grid import sample_position_grid


@pytest.fixture
def grid_module(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return import_module("grid_control_variate")


def quadratic_grid(module):
    ends = {"c0": (0., 0.), "fitted_c": (.1, .2)}

    def objective(arm, point):
        x, y = np.asarray(point) - ends[arm]
        return 100. + x*x + 2*y*y + .1*x*y

    grid = sample_position_grid(objective, ends)
    points = [module.xy(row) for row in grid["points"]]
    scores = {point: tuple(objective(arm, point) for arm in module.ARMS) for point in points}
    return points, list(ends.values()), scores


def test_research_grid_uses_only_original_exact_paid_locations(grid_module):
    points, ends, values = quadratic_grid(grid_module)
    calls = []

    def paid(point):
        calls.append(point)
        return values[point]

    result = grid_module.position_map(points, ends, 25., paid)
    assert set(result["estimated"]) | set(result["paid"]) == set(points)
    assert len(set(calls)) == len(calls) == len(result["paid"])
    assert set(calls).isdisjoint(result["estimated"])
    assert set(ends) <= set(calls)
    assert len(result["estimated"]) > 10
    check = grid_module.audit(points, values, result)
    assert all(grid_module.preserves_fidelity(row) for row in check.values())
    assert max(row["max_estimated_score_error"] for row in check.values()) < 1e-10


def test_sentinels_alone_cannot_prove_unqueried_low_mode_absent(grid_module):
    points, endpoints, values = quadratic_grid(grid_module)
    declared = grid_module.position_map(points, endpoints, 25., values.__getitem__)
    hidden = next(iter(declared["estimated"]))
    changed = dict(values)
    changed[hidden] = (60., 60.)
    alternate = grid_module.position_map(points, endpoints, 25., changed.__getitem__)
    assert declared == alternate
    check = grid_module.audit(points, changed, alternate)
    assert any(row["low_modes_removed"] for row in check.values())
    assert all(not grid_module.preserves_fidelity(row) for row in check.values())


def test_nonfinite_training_calls_exact_model_at_every_coordinate(grid_module):
    points, endpoints, values = quadratic_grid(grid_module)
    values[(-12.5, -12.5)] = (None, 123.)
    result = grid_module.position_map(points, endpoints, 25., values.__getitem__)
    assert not result["estimated"]
    assert result["paid"] == values
    assert "exact_fallback" in result["sources"].values()
