import numpy as np
import pytest
from position_overlap import coupling, precision


def test_only_position_overlap_modes_get_tighter_prior():
    result = precision([[1, 0, 0], [0, 2, 0]])
    np.testing.assert_allclose(result["precision"], np.diag([1/25**2, 1/25**2, 1/50**2]))
    assert result["rank"] == 2


def test_no_overlap_recovers_uniform_wide_prior():
    result = precision(np.zeros((2, 4)))
    assert result["rank"] == 0
    np.testing.assert_allclose(result["precision"], np.eye(4)/50**2)


def test_equal_sigmas_recover_uniform_control():
    result = precision([[1, 2, 3], [4, 5, 6]], wide_sigma=0.25, protected_sigma=0.25)
    np.testing.assert_allclose(result["precision"], np.eye(3)/25**2)


def test_basis_rotation_covariance_and_position_rotation_invariance():
    rng = np.random.default_rng(8401)
    cross = rng.normal(size=(2, 5))
    q = np.linalg.qr(rng.normal(size=(5, 5)))[0]
    p = precision(cross)["precision"]
    np.testing.assert_allclose(precision(cross @ q)["precision"], q.T @ p @ q, atol=1e-14)
    np.testing.assert_allclose(precision(np.array([[0, 1], [-1, 0]]) @ cross)["precision"],
                               p, atol=1e-14)


def test_quadratic_gradient_matches_finite_difference():
    p = precision([[1, 2, 3], [0, 2, 1]])["precision"]
    vector = np.array([20., -40., 100.])
    step = 1e-4
    finite = []
    for direction in np.eye(3) * step:
        plus, minus = vector + direction, vector - direction
        finite.append((0.5 * plus @ p @ plus - 0.5 * minus @ p @ minus) / (2 * step))
    np.testing.assert_allclose(p @ vector, finite, atol=1e-10, rtol=0)


def test_cross_information_matches_explicit_latent_design():
    rng = np.random.default_rng(8402)
    n, k = 7, 4
    basis = np.linalg.svd(np.ones((1, k)), full_matrices=True)[2][1:].T
    weights = rng.uniform(size=(n, k)) / k
    spatial = rng.normal(size=(n, k, 2))
    times, centers = np.arange(n), np.arange(k)
    actual = coupling(weights, spatial, times, centers, basis)
    expected = np.zeros_like(actual)
    for i in range(n):
        for j in range(k):
            expected += weights[i, j] * np.outer(spatial[i, j], basis[j]) * (
                times[i] - centers[j]) / 100
    np.testing.assert_allclose(actual, expected, atol=1e-14)


def test_rejects_nonfinite_and_invalid_prior():
    with pytest.raises(ValueError):
        precision([[float("nan")], [0]])
    with pytest.raises(ValueError):
        precision([[1], [2]], wide_sigma=0.25, protected_sigma=0.5)


def test_single_satellite_has_no_relative_slope_modes():
    result = precision(np.zeros((2, 0)))
    assert result["rank"] == 0 and result["precision"].shape == (0, 0)
