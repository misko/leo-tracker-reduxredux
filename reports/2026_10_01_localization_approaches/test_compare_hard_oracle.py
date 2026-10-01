from __future__ import annotations

import pytest
from compare_hard_oracle import _compare_fit, _fits_by_seed


def _fit(*, iterations=4, converged=True, objective=10., east=1., associations=None):
    return {
        "seed": {"east_km": 2., "north_km": 3.},
        "mean": [east, 2., 0., 0., 0.],
        "satellite_epoch_s": [0.],
        "objectives": [20., 15., objective],
        "iterations": iterations,
        "converged": converged,
        "reason": "objective_stable" if converged else "wall_budget",
        "associations": [1, 2] if associations is None else associations,
    }


def test_equal_coverage_distinguishes_equivalence_and_true_discrepancy():
    old = _fit()
    equivalent = _compare_fit(
        "unit", (2., 3.), _fit(east=1. + 1e-7), old,
        state_atol=1e-5, objective_atol=1e-5,
    )
    assert equivalent["classification"] == "equivalent_endpoint"
    discrepant = _compare_fit(
        "unit", (2., 3.), _fit(associations=[2, 1]), old,
        state_atol=1e-5, objective_atol=1e-5,
    )
    assert discrepant["classification"] == "numerical_discrepancy"


def test_budget_cut_is_separate_when_shared_objectives_match():
    old = _fit(iterations=8, converged=True)
    current = _fit(iterations=4, converged=False)
    row = _compare_fit(
        "unit", (2., 3.), current, old, state_atol=1e-5, objective_atol=1e-5
    )
    assert row["classification"] == "different_budget_coverage"


def test_seed_join_is_exact_and_rejects_duplicates():
    assert set(_fits_by_seed([_fit()])) == {(2., 3.)}
    with pytest.raises(ValueError, match="duplicate exact seed"):
        _fits_by_seed([_fit(), _fit()])
