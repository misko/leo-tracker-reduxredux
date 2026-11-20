"""Check strict contraction and the two-variable bounded fit."""

import numpy as np
import pytest

from tools.pipeline_eval.variants.v5_armijo_fit import STOP_KM, TRIALS, bounded_armijo


def solve(residual, initial, lower=(-2.0, -2.0), upper=(2.0, 2.0)):
    points = []

    def record(position):
        assert np.all((lower <= position) & (position <= upper))
        points.append(position.copy())
        return residual(position)

    fit = bounded_armijo(record, initial, lower, upper, iterations=48)
    assert fit["evaluations"] == len(points)
    assert fit["score"] == pytest.approx(np.sum(residual(fit["parameters"]) ** 2))
    history = fit["history"]
    assert all(a["score"] > b["score"] for a, b in zip(history, history[1:], strict=False))
    np.testing.assert_array_equal(history[-1]["parameters"], fit["parameters"])
    return fit, points


def test_curved_regression_contracts_a_rejected_feasible_point():
    def residual(position):
        return np.array([position[0] ** 2 - 1.0, position[1]])

    start = np.array([0.4, 0.0])
    fit, points = solve(residual, start)
    rejected, next_trial = points[3:5]
    assert np.linalg.norm(residual(rejected)) > np.linalg.norm(residual(start))
    np.testing.assert_allclose(next_trial - start, (rejected - start) / 2)
    assert sum(np.array_equal(point, rejected) for point in points) == 1
    assert np.linalg.norm(residual(next_trial)) < np.linalg.norm(residual(start))
    assert fit["rejected_trials"] >= 1
    assert fit["stopped"] == "small_bounded_step"
    np.testing.assert_allclose(fit["parameters"], [1.0, 0.0], atol=STOP_KM)


def test_all_rejected_trials_get_distinct_strictly_smaller_displacements():
    def residual(position):
        first = 1.0 - position[0] if position[0] <= 0.001 else 2.0
        return np.array([first, position[1]])

    fit, points = solve(residual, [0.0, 0.0])
    steps = [np.linalg.norm(x) for x in points[3:]]
    assert fit["stopped"] == "no_accepted_armijo_step"
    assert fit["rejected_trials"] == len(steps) == TRIALS
    assert all(following < earlier for earlier, following in zip(steps, steps[1:], strict=False))
    assert len(fit["history"]) == 1


def test_box_edge_solves_the_coupled_tangential_coordinate():
    matrix = np.array([[2.0, 1.0], [0.0, 2.0], [1.0, 2.0]])
    target = np.array([4.0, 0.3])
    normal = matrix.T @ matrix
    tangent = target[1] + normal[1, 0] * (target[0] - 2.0) / normal[1, 1]

    fit, _ = solve(lambda x: matrix @ (x - target), [5.0, -4.0])
    np.testing.assert_allclose(fit["parameters"], [2.0, tangent], atol=STOP_KM)
    assert fit["parameters"][0] == 2


@pytest.mark.parametrize("weak_axis", [0.0, 1e-10])
def test_singular_and_ill_conditioned_geometry_remain_finite(weak_axis):
    def residual(position):
        return np.array([position[0] - 1.1, weak_axis * (position[1] - 1.0)])

    fit, _ = solve(residual, [-1.7, 0.5])
    np.testing.assert_allclose(fit["parameters"], [1.1, 0.5], atol=STOP_KM)
    assert fit["stopped"] == "small_bounded_step"
