import numpy as np
import pytest
from joint_clock import JointClockObjective, fit

from leo.analysis.hard60_score import Hard60Objective
from leo.application.hard60_runner import HARD60_SCORE
from tests.analysis.test_regional_position_score import synthetic_inputs


def setup():
    obs, bank, prior = synthetic_inputs()
    nodes = np.array([0, 30, 60, 90.0])
    knots = np.array([[10, -10, -10, 10], [-20, 20, 20, -20.0]])
    interpolation = np.column_stack([np.interp(obs.times_s, nodes, row) for row in np.eye(4)])
    baseline = np.sum(interpolation * knots[obs.receiver], axis=1) + 15
    base = Hard60Objective(obs, bank, prior, HARD60_SCORE, receiver_baseline_hz=baseline)
    return base, JointClockObjective(base, nodes, knots)


def test_existing_correction_reproduces_score_plus_original_penalty_and_gauge():
    base, model = setup()
    v = np.array([3, -5, 10, 0.1, -10, -0.1, 25, 0.3, 0.1, -0.1])
    beta = model.initial_clock
    expected, gradient, terms = base.evaluate(v)
    actual, grad, _, extended = model.evaluate_joint(v, beta)
    assert actual == pytest.approx(expected + 0.5 * beta @ model.precision @ beta, abs=1e-10)
    np.testing.assert_allclose(grad, gradient, atol=1e-10, rtol=0)
    np.testing.assert_allclose(extended.residual_hz, terms.residual_hz, atol=1e-10)
    np.testing.assert_allclose(model.null.sum(axis=0), 0, atol=1e-12)
    np.testing.assert_allclose(model.nodes @ model.null, 0, atol=1e-12)


def test_all_joint_gradients_match_finite_differences():
    _, model = setup()
    v = np.array([3, -5, 10, 0.1, -10, -0.1, 25, 0.3, 0.1, -0.1])
    beta = model.initial_clock + 12
    _, gradient, extra, _ = model.evaluate_joint(v, beta)
    for i in range(len(v)):
        delta = np.eye(len(v))[i] * 1e-5
        numeric = (
            model.evaluate_joint(v + delta, beta)[0] - model.evaluate_joint(v - delta, beta)[0]
        ) / 2e-5
        assert numeric == pytest.approx(gradient[i], abs=5e-5)
    for i in range(len(beta)):
        delta = np.eye(len(beta))[i] * 0.001
        numeric = (
            model.evaluate_joint(v, beta + delta)[0] - model.evaluate_joint(v, beta - delta)[0]
        ) / 0.002
        assert numeric == pytest.approx(extra[i], abs=1e-7)


@pytest.mark.parametrize("arm", ["fitted-c", "zero-c"])
def test_joint_fit_retains_physical_bounds_and_rf_ablation(arm):
    _, model = setup()
    seed = np.array([3, -5, 10, 0.1, -10, -0.1, 25, 0.3, 0.1, -0.1])
    result = fit(model, seed, arm=arm, maximum_seconds=5)
    assert result["physical_constraints_minimum"] >= -1e-7
    assert result["converged"] == (result["stationarity"] <= 0.001)
    np.testing.assert_allclose(result["knots_hz"].sum(axis=1), 0, atol=1e-8)
    if arm == "zero-c":
        assert result["vector"][6] == 0
