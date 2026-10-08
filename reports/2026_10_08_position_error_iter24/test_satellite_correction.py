import sys
from pathlib import Path

import numpy as np
import pytest

REPORTS = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPORTS / f"2026_10_08_position_error_iter{n}") for n in ("19", "04", "10")]
from dynamic_rf import DynamicRFObjective, fit  # noqa: E402
from satellite_correction import SatelliteCorrection  # noqa: E402
from test_joint_clock import setup  # noqa: E402


def models(variant):
    base, old = setup()
    knots = old.initial_clock.reshape(2, -1) @ old.null.T
    centers = np.full(len(base.bank.numbers), base.observations.time_center_s)
    return DynamicRFObjective(base, old.nodes, knots, 50), SatelliteCorrection(
        base, old.nodes, knots, centers, variant
    )


@pytest.mark.parametrize("variant", ["offset", "slope", "both"])
def test_zero_correction_equivalence_and_gradients(variant):
    original, model = models(variant)
    seed = np.array([3, -5, 10, 0.1, -10, -0.1, 25, 0.3, 0.1, -0.1])
    old_clock = original.initial_clock.copy()
    old_clock[-2:] = [20, -10]
    clock = model.expand_clock(old_clock)
    expected = original.evaluate_joint(seed, old_clock)
    actual = model.evaluate_joint(seed, clock)
    np.testing.assert_allclose(actual[0], expected[0], atol=1e-10)
    np.testing.assert_allclose(actual[1], expected[1], atol=1e-10)
    clock[model.smooth_clock_count : model.slope_slice.stop] = 15
    offsets, slopes = model.physical_corrections(clock)
    assert abs(offsets.sum()) < 1e-10 and abs(slopes.sum()) < 1e-10
    _, physical, nuisance, _ = model.evaluate_joint(seed, clock)
    point = np.r_[seed, clock]
    numeric = []
    for delta in np.eye(len(point)) * 1e-4:
        plus, minus = point + delta, point - delta
        numeric.append(
            (
                model.evaluate_joint(plus[: len(seed)], plus[len(seed) :])[0]
                - model.evaluate_joint(minus[: len(seed)], minus[len(seed) :])[0]
            )
            / 2e-4
        )
    np.testing.assert_allclose(np.r_[physical, nuisance], numeric, atol=2e-4, rtol=2e-4)


@pytest.mark.parametrize("arm", ["fitted-c", "zero-c"])
def test_existing_fitter_and_rf_locks(arm):
    _, model = models("both")
    seed = np.array([3, -5, 10, 0.1, -10, -0.1, 25, 0.3, 0.1, -0.1])
    row = fit(model, seed, arm=arm, clock_seed=model.initial_clock)
    assert np.isfinite(row["objective"])
    assert max(abs(row["vector"][[3, 5]])) <= 60 + 1e-7
    assert row["physical_constraints_minimum"] >= -1e-7
    assert row["converged"] == (row["stationarity"] <= 0.001)
    if arm == "zero-c":
        assert row["vector"][6] == 0
        np.testing.assert_array_equal(row["rf_drift_coefficients"], [0, 0])
