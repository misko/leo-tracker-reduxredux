import numpy as np
import pytest

from leo.analysis.research.projected_position_information import projected_position_information


def test_projection_matches_dense_gaussian_schur_complement():
    rng = np.random.default_rng(14)
    a, b = rng.normal(size=(80, 2)), rng.normal(size=(80, 5))
    weights, prior = rng.uniform(0.2, 1, 80), np.array([0.0, 0.0, 0.3, 0.6, 1.0])
    result = projected_position_information(
        a, b, noise_hz=2, weights=weights, prior_precision=prior
    )
    normal = np.c_[a, b].T @ (weights[:, None] * np.c_[a, b]) / 4
    normal[2:, 2:] += np.diag(prior)
    expected = normal[:2, :2] - normal[:2, 2:] @ np.linalg.solve(normal[2:, 2:], normal[2:, :2])
    np.testing.assert_allclose(result["information_per_km2"], expected, rtol=1e-12, atol=1e-12)
    np.testing.assert_allclose(result["covariance_km2"], np.linalg.inv(expected), rtol=1e-12)


def test_nuisance_unit_changes_and_duplicate_gauges_do_not_change_projection():
    rng = np.random.default_rng(31)
    a, b = rng.normal(size=(40, 2)), rng.normal(size=(40, 3))
    expected = projected_position_information(a, b)["information_per_km2"]
    scaled = np.c_[b * [1e-12, 1e12, 1], b[:, 0]]
    actual = projected_position_information(a, scaled)["information_per_km2"]
    np.testing.assert_allclose(actual, expected, rtol=1e-12, atol=1e-12)


def test_complete_nuisance_confounding_is_unidentified_not_zero_uncertainty():
    a = np.c_[np.ones(20), np.linspace(-1, 1, 20)]
    result = projected_position_information(a, a[:, :1])
    assert result["position_rank"] == 1
    assert result["covariance_km2"] is None
    assert result["one_sigma_axes_km"] is None
    fully_confounded = projected_position_information(a, a)
    assert fully_confounded["position_rank"] == 0
    assert fully_confounded["covariance_km2"] is None


def test_priors_restore_confounded_information_and_no_nuisance_matches_raw():
    a = np.c_[np.ones(20), np.linspace(-1, 1, 20)]
    raw = projected_position_information(a, np.empty((20, 0)), noise_hz=1)
    np.testing.assert_allclose(raw["information_per_km2"], a.T @ a)
    weak = projected_position_information(a, a, noise_hz=1, prior_precision=[0.1, 0.1])
    strong = projected_position_information(a, a, noise_hz=1, prior_precision=[1, 1])
    assert weak["position_rank"] == 2
    assert np.all(strong["eigenvalues_per_km2"] > weak["eigenvalues_per_km2"])


@pytest.mark.parametrize(
    "kwargs", [{"noise_hz": 0}, {"weights": [-1] * 5}, {"prior_precision": [-1]}]
)
def test_invalid_scientific_inputs_are_rejected(kwargs):
    with pytest.raises(ValueError):
        projected_position_information(np.ones((5, 2)), np.ones((5, 1)), **kwargs)
