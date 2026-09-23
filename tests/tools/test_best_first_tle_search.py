# ruff: noqa: I001
"""Independent contracts for the bounded best-first TLE search."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest


ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "tools" / "research" / "best_first_tle_search.py"
SPEC = importlib.util.spec_from_file_location("best_first_tle_search_test", PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def residual(track_id, rms, weight=1.0, ids=()):
    return MODULE.TrackResidual(track_id, rms, weight, tuple(ids))


def flat_evaluator(calls, value=0.0):
    def evaluate(points):
        points = np.asarray(points, dtype=float)
        calls.extend(map(tuple, points))
        return [
            MODULE.point_evaluation(east, north, (residual("track", value, 1.0, ("obs",)),))
            for east, north in points
        ]

    return evaluate


def test_capped_all_track_objective_uses_timebin_weight_and_strict_200_diagnostics():
    mse, rmse, observations, qualifying_tracks = MODULE.weighted_all_track_objective(
        (
            residual("short", 100.0, 2.0, ("one", "shared")),
            residual("missing", None, 3.0),
            residual("at-threshold", 200.0, 1.0, ("two", "shared")),
            residual("over-cap", 1000.0, 4.0, ("three",)),
        )
    )

    expected = (2 * 100**2 + 3 * 800**2 + 200**2 + 4 * 800**2) / 10
    assert mse == expected
    assert rmse == pytest.approx(np.sqrt(expected))
    assert observations == 2  # strict <200: only "short" contributes its union
    assert qualifying_tracks == 1


def test_objective_rejects_nonpositive_or_nonfinite_timebin_weights():
    with pytest.raises(ValueError, match="weight"):
        MODULE.weighted_all_track_objective((residual("bad", 1.0, 0.0),))
    with pytest.raises(ValueError, match="weight"):
        MODULE.weighted_all_track_objective((residual("bad", 1.0, np.nan),))


def test_unmatched_track_never_contributes_to_200hz_diagnostic():
    _, _, observations, qualifying_tracks = MODULE.weighted_all_track_objective(
        (residual("missing", None, 1.0, ("must-not-count",)),),
        unmatched_penalty_hz=100.0,
    )

    assert observations == 0
    assert qualifying_tracks == 0


def test_effective_timebin_weight_ignores_duplicate_sample_density():
    sparse = np.asarray([10.05, 10.95, 11.01, 11.99, 13.0])
    duplicated = np.repeat(sparse, [9, 4, 7, 2, 11])

    assert MODULE.effective_one_second_bin_weight(sparse) == 3
    assert MODULE.effective_one_second_bin_weight(duplicated) == 3


def test_equal_certified_bound_is_retained_and_final_lattice_is_complete():
    calls = []
    result = MODULE.best_first_search(
        flat_evaluator(calls, value=0.0),
        radius_km=100.0,
        region_size_km=200.0,
        levels_km=(100.0, 50.0),
        budget_points=20,
        certified_lower_bound=lambda _cell, _parent, _cache: 0.0,
    )

    assert result.complete
    assert result.metrics["certified_prune_count"] == 0
    # The four 50 km corners are outside the 100 km circle.
    assert len(result.finest_evaluations) == 12
    assert len(calls) == len(set(calls)) == 16


def test_heuristic_drop_never_claims_global_completion():
    calls = []
    result = MODULE.best_first_search(
        flat_evaluator(calls, value=0.0),
        radius_km=100.0,
        region_size_km=200.0,
        levels_km=(100.0, 50.0),
        budget_points=20,
        estimate_priority=lambda _cell, _parent, _cache: 1.0,
        heuristic_discard_margin_hz2=0.0,
    )

    assert result.metrics["heuristic_drop_count"] > 0
    assert not result.complete
    assert "heuristic" in result.stop_reason


def test_strictly_worse_certified_bound_can_preserve_completion_guarantee():
    calls = []
    result = MODULE.best_first_search(
        flat_evaluator(calls, value=0.0),
        radius_km=100.0,
        region_size_km=200.0,
        levels_km=(100.0, 50.0),
        budget_points=20,
        certified_lower_bound=lambda _cell, _parent, _cache: 1.0,
    )

    assert result.complete
    assert result.metrics["certified_prune_count"] == 4
    assert not result.finest_evaluations
    assert result.metrics["result_guarantee"] == "exhaustive-with-certified-pruning-only"


def test_global_incumbent_and_best_finest_are_separately_reported():
    def evaluate(points):
        rows = []
        for east, north in points:
            coarse = abs(east) == 50.0 and abs(north) == 50.0
            rows.append(
                MODULE.point_evaluation(east, north, (residual("track", 0.0 if coarse else 1.0),))
            )
        return rows

    result = MODULE.best_first_search(
        evaluate,
        radius_km=100.0,
        region_size_km=200.0,
        levels_km=(100.0, 50.0),
        budget_points=20,
    )

    assert result.best is not None and result.best.weighted_mse_hz2 == 0.0
    assert result.best_finest is not None and result.best_finest.weighted_mse_hz2 == 1.0


def test_default_priority_uses_evaluated_child_cost_not_parent_cost():
    def evaluate(points):
        rows = []
        for east, north in points:
            # Fine child residuals differ from their parent residuals.
            value = float((east + 50.0) ** 2 + (north + 50.0) ** 2)
            rows.append(MODULE.point_evaluation(east, north, (residual("track", value),)))
        return rows

    result = MODULE.best_first_search(
        evaluate,
        radius_km=100.0,
        region_size_km=200.0,
        levels_km=(100.0, 50.0, 25.0),
        budget_points=100,
    )

    evaluated = {
        row["cell_id"]: row["weighted_mse_hz2"]
        for row in result.trace
        if row["event"] == "evaluate"
    }
    fine_pops = [
        row
        for row in result.trace
        if row["event"] == "pop" and row["depth"] > 0 and row["cell_id"] in evaluated
    ]
    assert fine_pops
    assert all(row["priority_hz2"] == evaluated[row["cell_id"]] for row in fine_pops)


def test_budget_limited_children_remain_deferred_not_silently_lost():
    calls = []
    result = MODULE.best_first_search(
        flat_evaluator(calls),
        radius_km=100.0,
        region_size_km=200.0,
        levels_km=(100.0, 50.0),
        budget_points=5,
    )

    deferred = {(cell.depth, cell.east_km, cell.north_km) for cell in result.deferred_cells}
    # The first parent is (-50,-50). After its first child consumes the single
    # remaining point, its three other in-circle children must remain visible.
    assert (1, -75.0, -25.0) in deferred
    assert (1, -25.0, -75.0) in deferred
    assert (1, -25.0, -25.0) in deferred
    assert not result.complete
    assert result.stop_reason == "point-budget-reached"


def test_outside_parent_is_kept_when_an_aligned_child_reaches_circle_rim():
    calls = []
    MODULE.best_first_search(
        flat_evaluator(calls),
        radius_km=445.0,
        region_size_km=1000.0,
        levels_km=(100.0, 50.0),
        budget_points=200,
        estimate_priority=lambda cell, _parent, _cache: (
            -1.0 if (cell.east_km, cell.north_km) == (450.0, 50.0) else 1.0
        ),
    )

    # (450,50) is outside the circle; its (425,25) 50 km child is inside.
    assert (425.0, 25.0) in set(calls)


def test_levels_must_be_exact_aligned_halvings_and_evaluator_order_is_preserved():
    with pytest.raises(ValueError, match="aligned halvings"):
        MODULE.best_first_search(
            lambda _points: (),
            radius_km=100.0,
            region_size_km=200.0,
            levels_km=(100.0, 40.0),
            budget_points=20,
        )
    with pytest.raises(ValueError, match="coordinate order"):
        MODULE.best_first_search(
            lambda points: [
                MODULE.point_evaluation(-points[0, 0], points[0, 1], (residual("track", 0.0),))
                for _ in points
            ],
            radius_km=100.0,
            region_size_km=200.0,
            levels_km=(100.0,),
            budget_points=20,
        )
