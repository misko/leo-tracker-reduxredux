import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "2026_10_08_position_error_iter04"))
from test_joint_clock import setup  # noqa: E402
from timing_fit import fit  # noqa: E402


@pytest.mark.parametrize("arm", ["fitted-c", "zero-c"])
def test_tight_timing_bound_projects_seed_and_is_enforced(arm):
    _, model = setup()
    seed = np.array([3, -5, 10, 0.1, -10, -0.1, 25, 8, 0.1, -0.1])
    row = fit(model, seed, arm=arm, timing_half_width_s=1)
    vector = row["vector"]
    assert max(abs(vector[7] + model.basis @ vector[8:])) <= 1 + 1e-7
    assert max(abs(vector[[3, 5]])) <= 60 + 1e-7
    assert row["physical_constraints_minimum"] >= -1e-7
    if arm == "zero-c":
        assert vector[6] == 0


def test_invalid_timing_bound_rejected():
    _, model = setup()
    seed = np.array([3, -5, 10, 0.1, -10, -0.1, 25, 0, 0.1, -0.1])
    with pytest.raises(ValueError, match="invalid timing bound"):
        fit(model, seed, arm="fitted-c", timing_half_width_s=0)


def test_candidate_removal_preserves_observations_and_retained_total_shifts():
    from experiment import reduce_bank

    from leo.analysis.hard60_score import Hard60Objective

    base, _ = setup()
    bank = replace(
        base.bank,
        numbers=np.arange(1, 6),
        position_km=base.bank.position_km[[0, 1, 2, 0, 1]],
        velocity_km_s=base.bank.velocity_km_s[[0, 1, 2, 0, 1]],
    )
    base = Hard60Objective(
        base.observations, bank, base.prior, base.score, receiver_baseline_hz=base.baseline
    )
    relative = np.array([-6, 1, 1, 2, 2.0])
    seed = np.r_[3, -5, 10, 0.1, -10, -0.1, 25, 0.7, base.basis.T @ relative]
    subset, projected, removed = reduce_bank(base, seed, 5)
    assert removed == [1]
    assert subset.observations is base.observations
    np.testing.assert_array_equal(subset.bank.numbers, [2, 3, 4, 5])
    np.testing.assert_allclose(projected[7] + subset.basis @ projected[8:], relative[1:] + 0.7)
