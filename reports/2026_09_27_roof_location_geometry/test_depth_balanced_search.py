from types import SimpleNamespace

import numpy as np
import pytest

import depth_balanced_search as balanced
import measured_search


def evaluator(function):
    return lambda points: tuple(SimpleNamespace(
        east_km=float(east), north_km=float(north),
        weighted_mse_hz2=float(function(float(east), float(north))))
        for east, north in points)


def test_budget_boundary_and_no_phantom_priorities():
    result = balanced.search(
        evaluator(lambda east, north: 1 + east**2 + north**2),
        radius_km=250., budget_points=160)
    assert len(result.all_evaluations) == 160
    assert result.stop_reason == "point-budget-reached"
    evaluated = {(row.east_km, row.north_km): row.weighted_mse_hz2
                 for row in result.all_evaluations}
    assert all(np.hypot(*point) <= 250 + 1e-10 for point in evaluated)
    for event in result.trace:
        if event["event"] == "pop":
            point = tuple(event["representative"])
            assert point in evaluated
            assert event["measured_priority"] == evaluated[point]
    assert sum(event["event"] == "evaluate" for event in result.trace) == len(evaluated)


def test_boundary_representatives_stay_in_cell_and_disk():
    result = balanced.search(
        evaluator(lambda east, north: east + 2 * north), radius_km=150.,
        region_size_km=400., levels_km=(100., 50., 25.), budget_points=60)
    evaluations = [event for event in result.trace if event["event"] == "evaluate"]
    for event in evaluations:
        assert np.hypot(event["east_km"], event["north_km"]) <= 150 + 1e-10
        half = event["spacing_km"] / 2
        assert abs(event["east_km"] - event["cell_east_km"]) <= half + 1e-10
        assert abs(event["north_km"] - event["cell_north_km"]) <= half + 1e-10


def test_deterministic_evaluations_and_trace():
    kwargs = dict(radius_km=150., region_size_km=400.,
                  levels_km=(100., 50., 25., 12.5), budget_points=64)
    objective = evaluator(lambda east, north: (east - 37)**2 + (north + 19)**2)
    first = balanced.search(objective, **kwargs)
    second = balanced.search(objective, **kwargs)
    assert first.all_evaluations == second.all_evaluations
    assert first.trace == second.trace


def test_depth_balance_reaches_narrow_basin_starved_by_global_heap():
    # The broad basin keeps producing attractive descendants.  The narrow
    # basin is only revealed after a less-attractive coarse cell is refined.
    def objective(east, north):
        narrow_distance = np.hypot(east + 25., north - 75.)
        if narrow_distance < 18:
            return -20 + narrow_distance**2 / 100
        return ((east + 50.)**2 + (north + 50.)**2) / 10000

    kwargs = dict(radius_km=200., region_size_km=400.,
                  levels_km=(100., 50., 25., 12.5), budget_points=64)
    depth_result = balanced.search(evaluator(objective), **kwargs)
    global_result = measured_search.search(evaluator(objective), **kwargs)
    assert depth_result.global_incumbent.weighted_mse_hz2 < -10
    assert np.hypot(depth_result.global_incumbent.east_km + 25,
                    depth_result.global_incumbent.north_km - 75) < 18
    assert global_result.global_incumbent.weighted_mse_hz2 >= 0


def test_validation_and_nonfinite_scores_fail_closed():
    with pytest.raises(ValueError, match="initial"):
        balanced.search(evaluator(lambda *_: 0), budget_points=1)
    with pytest.raises(ValueError, match="nonfinite"):
        balanced.search(evaluator(lambda *_: np.nan), radius_km=100.,
                        region_size_km=200., levels_km=(100., 50.), budget_points=8)
