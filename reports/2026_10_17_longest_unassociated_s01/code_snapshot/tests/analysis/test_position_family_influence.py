import numpy as np
import pytest

from leo.analysis.research.position_family_influence import tangent_position_step


def test_augmented_step_matches_dense_joint_solve_with_nonzero_prior_means():
    rng = np.random.default_rng(17)
    a, b = rng.normal(size=(40, 2)), rng.normal(size=(40, 4))
    r, n = rng.normal(size=40), rng.normal(size=4)
    w, p = rng.uniform(0.2, 1, 40), np.array([0, 0.1, 0.3, 0.7])
    result = tangent_position_step(a, b, r, n, w, p, noise_hz=2)
    d = np.c_[a, b]
    normal = d.T @ (w[:, None] * d) / 4 + np.diag(np.r_[0, 0, p])
    rhs = d.T @ (w * r) / 4 - np.r_[0, 0, p * n]
    expected = np.linalg.solve(normal, rhs)
    np.testing.assert_allclose(result["east_north_step_km"], expected[:2], atol=1e-12)
    np.testing.assert_allclose(result["nuisance_step"], expected[2:], atol=1e-12)
    assert result["quadratic_after"] <= result["quadratic_before"]


def test_metre_and_hz_unit_changes_do_not_change_position_step():
    rng = np.random.default_rng(77)
    a, b, r = rng.normal(size=(35, 2)), rng.normal(size=(35, 2)), rng.normal(size=35)
    base = tangent_position_step(a, b, r, [3, -2], np.ones(35), [0.1, 0.3])
    factor = np.array([1e-7, 1e7])
    changed = tangent_position_step(
        a, b * factor, r, np.array([3, -2]) / factor, np.ones(35), np.array([0.1, 0.3]) * factor**2
    )
    np.testing.assert_allclose(
        base["east_north_step_km"], changed["east_north_step_km"], atol=1e-12
    )


def test_negative_observation_weights_are_rejected():
    with pytest.raises(ValueError):
        tangent_position_step(np.ones((5, 2)), np.ones((5, 1)), np.zeros(5), [0], [-1] * 5, [1])
