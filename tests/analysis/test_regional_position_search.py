import numpy as np
import pytest

from leo.analysis.adaptive_tle_position import AdaptivePointScore, adaptive_best_first_search
from leo.analysis.regional_position_search import distinct_basins, hierarchical_search


def loss(east, north):
    return float((east + 82) ** 2 + (north + 74) ** 2)


def test_scalar_hierarchy_matches_baseline_cell_sequence():
    def baseline(points):
        return tuple(
            AdaptivePointScore(e, n, loss(e, n), np.sqrt(loss(e, n)), 20, 2, 2, 0, ())
            for e, n in points
        )

    old = adaptive_best_first_search(baseline, radius_km=250, budget_points=100)
    new = hierarchical_search(loss, budget_points=100)
    old_points = [(r["east_km"], r["north_km"]) for r in old.trace if r["event"] == "evaluate"]
    assert [(r.east_km, r.north_km) for r in new.evaluations] == old_points
    assert new.selected.score == old.global_incumbent.weighted_mse_hz2
    assert new.stop_reason == "point-budget"
    assert new.deferred_cells > 0
    assert all(np.hypot(r.east_km, r.north_km) <= 250 for r in new.evaluations)


def test_separate_objectives_can_explore_different_regions():
    left = hierarchical_search(loss, budget_points=100)
    right = hierarchical_search(lambda e, n: loss(-e, -n), budget_points=100)
    assert left.selected.east_km < 0 < right.selected.east_km
    assert {(p.east_km, p.north_km) for p in left.evaluations} != {
        (p.east_km, p.north_km) for p in right.evaluations
    }
    basins = distinct_basins(left, count=3, minimum_separation_km=25)
    assert len(basins) == 3
    for i, first in enumerate(basins):
        for second in basins[i + 1 :]:
            assert np.hypot(first.east_km - second.east_km, first.north_km - second.north_km) >= 25


def test_explicit_budget_and_bad_evaluator():
    with pytest.raises(ValueError, match="initial centers"):
        hierarchical_search(loss, budget_points=1)
    with pytest.raises(ValueError, match="nonfinite"):
        hierarchical_search(lambda e, n: float("nan"))
    with pytest.raises(ValueError, match="hierarchy"):
        hierarchical_search(loss, levels_km=(100, 20))
