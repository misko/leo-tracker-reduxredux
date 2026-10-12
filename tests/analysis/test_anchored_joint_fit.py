from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.anchored_joint_fit import fit_anchored_joint
from leo.analysis.hard60_dynamic_rf import fit
from tests.analysis.test_hard60_satellite_correction import models


def test_same_anchor_and_start_reproduce_the_existing_solver():
    _, model = models("both")
    seed = np.array([3.0, -5.0, 10.0, 0.1, -10.0, -0.1, 25.0, 0.3, 0.1, -0.1])
    options = dict(arm="fitted-c", clock_seed=model.initial_clock, maximum_seconds=20)
    old = fit(model, seed, **options)
    anchored = fit_anchored_joint(model, seed, local_center=seed[:2], **options)
    assert old["converged"] == anchored["converged"]
    assert old["objective"] == pytest.approx(anchored["objective"], abs=1e-9)
    np.testing.assert_array_equal(old["vector"], anchored["vector"])
    np.testing.assert_array_equal(old["clock_coefficients"], anchored["clock_coefficients"])


def quadratic_model(target):
    _, model = models("both")
    vector_target = np.zeros(model.size)
    vector_target[:2] = target

    def evaluate(vector, clock):
        delta = vector - vector_target
        value = 0.5 * (delta @ delta + clock @ clock)
        terms = SimpleNamespace(responsibilities=np.ones((1, 1)), residual_hz=np.zeros((1, 1)))
        return value, delta, clock.copy(), terms

    model.evaluate_joint = evaluate
    return model


def test_a_transported_start_does_not_move_the_original_local_disk():
    model = quadratic_model((30.0, 0.0))
    seed = np.zeros(model.size)
    seed[:2] = (24.0, 0.0)
    result = fit_anchored_joint(
        model,
        seed,
        arm="fitted-c",
        local_center=(0.0, 0.0),
        clock_seed=np.zeros_like(model.initial_clock),
        maximum_seconds=5,
    )
    assert result["converged"]
    assert result["vector"][0] == pytest.approx(25.0, abs=1e-6)
    assert np.linalg.norm(result["vector"][:2]) <= 25.0 + 1e-7
    assert result["physical_constraints_minimum"] >= -1e-7
    np.testing.assert_array_equal(result["local_center_km"], [0.0, 0.0])
    outside = seed.copy()
    outside[0] = 26.0
    with pytest.raises(ValueError, match="infeasible"):
        fit_anchored_joint(model, outside, arm="fitted-c", local_center=(0.0, 0.0))


def test_zero_c_locks_are_preserved_with_an_independent_anchor():
    model = quadratic_model((2.0, -3.0))
    seed = np.zeros(model.size)
    seed[6] = 300.0
    clock = np.zeros_like(model.initial_clock)
    clock[-2:] = [30.0, -40.0]
    result = fit_anchored_joint(
        model, seed, arm="zero-c", local_center=(0.0, 0.0), clock_seed=clock
    )
    assert result["converged"] and result["vector"][6] == 0.0
    np.testing.assert_array_equal(result["clock_coefficients"][-2:], [0.0, 0.0])


def test_a_feasible_unfinished_state_is_not_labeled_converged():
    model = quadratic_model((20.0, 7.0))
    target = np.zeros(model.size)
    target[:2] = (20.0, 7.0)
    hessian = np.eye(model.size)
    hessian[:2, :2] = [[4.0, 1.0], [1.0, 1.0]]

    def evaluate(vector, clock):
        delta = vector - target
        terms = SimpleNamespace(responsibilities=np.ones((1, 1)), residual_hz=np.zeros((1, 1)))
        return 0.5 * (delta @ hessian @ delta + clock @ clock), hessian @ delta, clock.copy(), terms

    model.evaluate_joint = evaluate
    result = fit_anchored_joint(
        model,
        np.zeros(model.size),
        arm="fitted-c",
        local_center=(0.0, 0.0),
        clock_seed=np.zeros_like(model.initial_clock),
        maximum_iterations=1,
    )
    assert not result["converged"] and result["stationarity"] > 0.001
    assert result["best_feasible_objective"] <= result["initial_objective"]
