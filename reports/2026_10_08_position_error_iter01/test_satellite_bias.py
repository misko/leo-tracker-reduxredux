import numpy as np
import pytest
from satellite_bias import BiasObjective, fit

from leo.analysis.hard60_score import Hard60Objective
from leo.application.hard60_runner import HARD60_SCORE
from tests.analysis.test_regional_position_score import synthetic_inputs


def objective():
    obs, bank, prior = synthetic_inputs()
    return Hard60Objective(obs, bank, prior, HARD60_SCORE)


def test_zero_bias_exactly_recovers_original_likelihood_and_gradient():
    base = objective()
    extension = BiasObjective(base, 150)
    vector = np.array([3, -5, 10, 0.1, -10, -0.1, 25, 0.3, 0.1, -0.1])
    expected, gradient, _ = base.evaluate(vector)
    actual, extended_gradient, _, _ = extension.evaluate_bias(vector, np.zeros(3))
    assert actual == pytest.approx(expected, abs=1e-12)
    np.testing.assert_allclose(extended_gradient, gradient, atol=1e-12, rtol=0)


def test_bias_and_physical_gradient_match_finite_differences():
    model = BiasObjective(objective(), 150)
    vector = np.array([3, -5, 10, 0.1, -10, -0.1, 25, 0.3, 0.1, -0.1])
    bias = np.array([30, -50, 90], float)
    _, gradient, bias_gradient, _ = model.evaluate_bias(vector, bias)
    for index in range(len(vector)):
        delta = np.eye(len(vector))[index] * 1e-5
        numeric = (
            model.evaluate_bias(vector + delta, bias)[0]
            - model.evaluate_bias(vector - delta, bias)[0]
        ) / 2e-5
        assert numeric == pytest.approx(gradient[index], abs=5e-5)
    for index in range(len(bias)):
        delta = np.eye(len(bias))[index] * 1e-3
        numeric = (
            model.evaluate_bias(vector, bias + delta)[0]
            - model.evaluate_bias(vector, bias - delta)[0]
        ) / 2e-3
        assert numeric == pytest.approx(bias_gradient[index], abs=1e-7)


@pytest.mark.parametrize("arm", ["fitted-c", "zero-c"])
def test_optimizer_keeps_physical_bounds_and_reports_audit(arm):
    base = objective()
    seed = np.array([3, -5, 10, 0.1, -10, -0.1, 25, 0.3, 0.1, -0.1])
    result = fit(base, seed, variant="satellite-bias-50", arm=arm, maximum_seconds=5)
    assert result["physical_constraints_minimum"] >= -1e-7
    assert np.max(abs(result["vector"][[3, 5]])) <= 60 + 1e-8
    assert np.max(abs(result["bias_hz"])) <= 2000 + 1e-7
    assert result["converged"] == (result["stationarity"] <= 0.001)
    if arm == "zero-c":
        assert result["vector"][6] == 0
