import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from ds789_correlated_residual import independent_t, kernel, multivariate_t, quadratic


def test_one_observation_matches_univariate_and_repeated_times_are_positive_definite():
    r = np.array([[10.0], [-300.0]])
    q, ld = quadratic(r, kernel([0], 10))
    np.testing.assert_allclose(multivariate_t(q, ld, 1, 100), independent_t(r, 100))
    assert np.linalg.eigvalsh(kernel([0, 0, 1], 60)).min() >= 0.199999999
    np.testing.assert_array_equal(kernel([0, 0], 0), np.eye(2))
    with pytest.raises(ValueError):
        kernel([], 1)


def test_conditional_density_matches_schur_complement_student_t():
    times = np.array([0.0, 1.0, 3.0, 6.0])
    residual = np.array([[10.0, -20.0, 30.0, 100.0]])
    scale, df = 70.0, 4
    covariance = kernel(times, 10) * scale**2
    training = np.array([0, 2])
    held = np.array([1, 3])
    a = covariance[np.ix_(training, training)]
    b = covariance[np.ix_(held, training)]
    c = covariance[np.ix_(held, held)]
    train = residual[:, training]
    qt, ldt = quadratic(train, a)
    qj, ldj = quadratic(residual, covariance)
    ratio = multivariate_t(qj, ldj, 4, 1) - multivariate_t(qt, ldt, 2, 1)
    mean = b @ np.linalg.solve(a, train[0])
    conditional_scale = (df + qt[0]) / (df + 2) * (c - b @ np.linalg.solve(a, b.T))
    qc, ldc = quadratic(residual[:, held] - mean, conditional_scale)
    direct = multivariate_t(qc, ldc, 2, 1, df=df + 2)
    np.testing.assert_allclose(ratio, direct, atol=1e-12)
    # Zero correlation still shares a latent track scale; it is not iid Student-t.
    qi, ldi = quadratic(residual, np.eye(4))
    assert not math.isclose(
        float(multivariate_t(qi, ldi, 4, scale)[0]), float(independent_t(residual, scale)[0])
    )
