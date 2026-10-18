"""Dense covariance and finite-difference oracles for orbital marginalization."""

import numpy as np
import pytest

from leo.analysis.research.orbit_phase_geometry import phase_frequency_grid
from leo.analysis.research.orbit_uncertainty import (
    low_rank_marginal,
    paired_frequency_modes,
    project_constant_features,
)


def test_marginal_quadratic_volume_and_coefficient_equal_dense_covariance():
    rng = np.random.default_rng(392)
    n = 17
    a = rng.normal(size=(n, n))
    noise = a @ a.T + np.eye(n) * 20
    w = np.linalg.inv(np.linalg.cholesky(noise))
    y = rng.normal(size=n) * 100
    f = rng.normal(size=(n, 3)) * 7
    r, u, base = project_constant_features(y, f, w, bias_sigma=30)
    actual = low_rank_marginal(r, u, n, base_logvolume=base)
    covariance = noise + 30**2 * np.ones((n, n)) + f @ f.T
    expected = y @ np.linalg.solve(covariance, y)
    np.testing.assert_allclose(actual["quadratic"], expected, rtol=1e-10)
    expected_log = np.linalg.slogdet(covariance)[1] - np.linalg.slogdet(noise)[1]
    assert actual["logvolume"] == pytest.approx(expected_log, rel=1e-10)
    np.testing.assert_allclose(
        actual["coefficient"], f.T @ np.linalg.solve(covariance, y), rtol=1e-10
    )
    assert actual["residual"] @ actual["residual"] == pytest.approx(expected + expected_log)


def test_student_objective_counts_observations_not_augmented_bias_coordinates():
    r = np.array([1.0, 2.0, 3.0, 4.0])
    u = np.array([[1.0], [2.0], [0.0], [0.0]])
    gaussian = low_rank_marginal(r, u, 3)
    student = low_rank_marginal(r, u, 3, degrees_of_freedom=4)
    expected = 7 * np.log1p(gaussian["quadratic"] / 4) + gaussian["logvolume"]
    assert student["residual"] @ student["residual"] == pytest.approx(expected)
    np.testing.assert_allclose(student["coefficient"], gaussian["coefficient"])


def test_rank_zero_collinear_modes_and_covariance_volume_penalty():
    r = np.array([2.0, -2.0, 1.0])
    zero = low_rank_marginal(r, np.empty((3, 0)), 3)
    np.testing.assert_allclose(zero["residual"][:-1], r)
    moderate = low_rank_marginal(r, r[:, None], 3)
    huge = low_rank_marginal(r, r[:, None] * 1e9, 3)
    assert huge["residual"] @ huge["residual"] > moderate["residual"] @ moderate["residual"]
    duplicated = low_rank_marginal(r, np.column_stack((r, r)), 3)
    assert np.isfinite(duplicated["residual"]).all()
    np.testing.assert_array_equal(r, [2, -2, 1])


def test_frequency_modes_match_dense_central_differences_with_shared_phase():
    knots = np.arange(-20.0, 321.0, 5)
    position = np.array([-2400.0, -4700, 4300])[None, :] + knots[:, None] * [2, -3, 0.5]
    velocity = np.broadcast_to([2.0, -3, 0.5], position.shape).copy()
    bank = dict(time_s=knots, position_km=position[None], velocity_km_s=velocity[None])
    dp = np.broadcast_to([0.2, 0.1, -0.05], (2, *position.shape)).copy()
    dv = np.broadcast_to([0.001, -0.002, 0.003], dp.shape).copy()
    modes = dict(time_s=knots, position_km=dp, velocity_km_s=dv)
    t = np.array([3.0, 70.0, 180.0, 180.0])
    labels = np.zeros(4, int)
    phases = np.array([2.1])
    actual = paired_frequency_modes(
        bank, modes, t, labels, phases, 37.906, -122.545, altitude_m=275
    )
    for k in range(2):
        values = []
        for sign in (1, -1):
            p = {name: value.copy() for name, value in bank.items()}
            p["position_km"][0] += sign * 1e-3 * dp[k]
            p["velocity_km_s"][0] += sign * 1e-3 * dv[k]
            values.append(
                phase_frequency_grid(p, t, 37.906, -122.545, phase_seconds=phases, altitude_m=275)[
                    0
                ][0]
            )
        np.testing.assert_allclose(actual[:, k], (values[0] - values[1]) / 0.002, atol=1e-5)


def test_invalid_nonfinite_covariance_inputs_fail_explicitly():
    with pytest.raises(ValueError):
        low_rank_marginal(np.ones(3), np.ones((4, 1)), 3)
    with pytest.raises(ValueError):
        low_rank_marginal(np.ones(3), np.ones((3, 1)), 3, degrees_of_freedom=0)
