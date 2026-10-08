import numpy as np
import pytest
from receiver_rf import ReceiverRFObjective, fit

from leo.analysis.hard60_score import Hard60Objective
from leo.application.hard60_runner import HARD60_SCORE
from tests.analysis.test_regional_position_score import synthetic_inputs


def base():
    obs, bank, prior = synthetic_inputs()
    return Hard60Objective(obs, bank, prior, HARD60_SCORE)


def test_original_equivalence_and_extended_gradient():
    original = base()
    model = ReceiverRFObjective(original, 150)
    v = np.array([3, -5, 10, 0.1, -10, -0.1, 25, 0.3, 0.1, -0.1])
    value, gradient, _ = original.evaluate(v)
    actual, grad, _, _ = model.evaluate_extended(v, 0)
    assert actual == pytest.approx(value, abs=1e-12)
    np.testing.assert_allclose(grad, gradient, atol=1e-12, rtol=0)
    _, grad, derivative, _ = model.evaluate_extended(v, 70)
    for index in range(len(v)):
        delta = np.eye(len(v))[index] * 1e-5
        numeric = (
            model.evaluate_extended(v + delta, 70)[0] - model.evaluate_extended(v - delta, 70)[0]
        ) / 2e-5
        assert numeric == pytest.approx(grad[index], abs=5e-5)
    numeric = (
        model.evaluate_extended(v, 70.001)[0] - model.evaluate_extended(v, 69.999)[0]
    ) / 0.002
    assert numeric == pytest.approx(derivative, abs=1e-7)


@pytest.mark.parametrize("arm", ["zero-c", "fitted-c"])
def test_constraints_and_complete_rf_ablation(arm):
    v = np.array([3, -5, 10, 0.1, -10, -0.1, 25, 0.3, 0.1, -0.1])
    result = fit(base(), v, sigma=150, arm=arm, maximum_seconds=5)
    assert result["physical_constraints_minimum"] >= -1e-7
    assert np.max(abs(result["vector"][[3, 5]])) <= 60 + 1e-7
    assert result["converged"] == (result["stationarity"] <= 0.001)
    if arm == "zero-c":
        assert result["vector"][6] == result["difference_hz_per_ghz"] == 0
