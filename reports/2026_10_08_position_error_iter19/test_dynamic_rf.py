import sys
from pathlib import Path

import numpy as np
import pytest

sys.path[:0] = [
    str(Path(__file__).resolve().parent.parent / "2026_10_08_position_error_iter04"),
    str(Path(__file__).resolve().parent.parent / "2026_10_08_position_error_iter10"),
]
from dynamic_rf import DynamicRFObjective, fit  # noqa: E402
from test_joint_clock import setup  # noqa: E402
from timing_fit import JointClockObjective  # noqa: E402


def models(sigma=150):
    base, old = setup()
    knots = old.initial_clock.reshape(2, -1) @ old.null.T
    return JointClockObjective(base, old.nodes, knots, 4), DynamicRFObjective(
        base, old.nodes, knots, sigma
    )


def test_zero_drift_reproduces_clock_model():
    old, model = models()
    seed = np.array([3, -5, 10, 0.1, -10, -0.1, 25, 0.3, 0.1, -0.1])
    expected = old.evaluate_joint(seed, old.initial_clock)
    actual = model.evaluate_joint(seed, model.initial_clock)
    np.testing.assert_allclose(actual[0], expected[0], atol=1e-10)
    np.testing.assert_allclose(actual[1], expected[1], atol=1e-10)
    np.testing.assert_allclose(actual[2][:-2], expected[2], atol=1e-10)


def test_dynamic_rf_and_physical_derivatives():
    _, model = models()
    seed = np.array([3, -5, 10, 0.1, -10, -0.1, 25, 0.3, 0.1, -0.1])
    clock = model.initial_clock.copy()
    clock[-2:] = [80, -40]
    _, gradient, nuisance, _ = model.evaluate_joint(seed, clock)
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
    np.testing.assert_allclose(np.r_[gradient, nuisance], numeric, atol=2e-4, rtol=2e-4)


@pytest.mark.parametrize("arm,sigma", [("zero-c", 150), ("fitted-c", 0), ("fitted-c", 150)])
def test_fit_locks_ablation_terms_and_preserves_bounds(arm, sigma):
    _, model = models(sigma)
    seed = np.array([3, -5, 10, 0.1, -10, -0.1, 25, 0.3, 0.1, -0.1])
    clock = model.initial_clock.copy()
    clock[-2:] = [80, -40]
    result = fit(model, seed, arm=arm, clock_seed=clock)
    assert max(abs(result["rf_drift_coefficients"])) <= 1000 + 1e-7
    assert max(abs(result["vector"][[3, 5]])) <= 60 + 1e-7
    assert result["physical_constraints_minimum"] >= -1e-7
    assert result["converged"] == (result["stationarity"] <= 0.001)
    if arm == "zero-c" or sigma == 0:
        np.testing.assert_array_equal(result["rf_drift_coefficients"], [0, 0])
    if arm == "zero-c":
        assert result["vector"][6] == 0
