"""Independent covariance and state-projection tests for causal orbit priors."""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from dsx01_causal_correlation import (  # noqa: E402
    project_state_difference,
    variance_matched_correlation,
)
from dsx01_joint_marginal import integrated_gaussian  # noqa: E402


@pytest.mark.parametrize("fraction", [0.0, 0.5, 0.9])
def test_correlations_preserve_each_marginal_and_positive_variance_floor(fraction):
    direction = np.array([4.0, -2.0, 0.0, 0.5, 1.0, -1.0])
    c = variance_matched_correlation(direction, fraction)
    np.testing.assert_allclose(np.diag(c), 1, atol=1e-15)
    assert np.linalg.eigvalsh(c).min() >= 1 - fraction - 1e-14
    assert c[0, 1] <= 0 and c[0, 2] == 0
    np.testing.assert_array_equal(variance_matched_correlation(np.zeros(6), fraction), np.eye(6))


def test_latent_transform_gives_dense_gaussian_density_and_physical_posterior():
    rng = np.random.default_rng(8)
    u = rng.normal(size=(12, 4))
    y = rng.normal(size=12)
    c = variance_matched_correlation([2.0, -1.0, 0.5, 0.3], 0.9)
    transform = np.linalg.cholesky(c)
    result = integrated_gaussian(y, u @ transform, 2.0)
    covariance = 4 * np.eye(len(y)) + u @ c @ u.T
    expected = (
        y @ np.linalg.solve(covariance, y) + np.linalg.slogdet(covariance)[1] - len(y) * np.log(4)
    )
    assert result["residual"] @ result["residual"] == pytest.approx(expected, abs=1e-12)
    mean = transform @ result["coefficient"]
    np.testing.assert_allclose(mean, c @ u.T @ np.linalg.solve(covariance, y), atol=1e-14)
    assert mean @ np.linalg.solve(c, mean) == pytest.approx(
        result["coefficient"] @ result["coefficient"]
    )


def test_state_projection_recovers_known_correlated_parameter_changes():
    rng = np.random.default_rng(19)
    up = rng.normal(size=(6, 3, 3))
    uv = rng.normal(size=(6, 3, 3)) / 150
    truth = np.array([0.4, -2.0, 0.1, 0.7, -0.3, 1.0])
    dp = np.einsum("k,ktd->td", truth, up)
    dv = np.einsum("k,ktd->td", truth, uv)
    fit = project_state_difference(dp, dv, up, uv)
    np.testing.assert_allclose(fit["coefficient"], truth, atol=1e-14)
    assert fit["rank"] == 6 and fit["unexplained_fraction"] < 1e-25


def test_invalid_correlation_rejected():
    with pytest.raises(ValueError, match="fraction"):
        variance_matched_correlation([1.0, 2.0], 1.0)
