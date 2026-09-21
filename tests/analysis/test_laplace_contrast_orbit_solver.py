import numpy as np
from scipy.integrate import quad

from leo.analysis.research.laplace_contrast_orbit_solver import (
    LaplaceContrastOrbitConfig,
    LaplaceContrastOrbitData,
    bounded_laplace_adjustment,
    fit_laplace_contrast_orbit,
)
from tests.analysis.test_formal_orbit import _synthetic


def test_bounded_laplace_adjustment_matches_dense_scalar_quadrature():
    rate, curvature, bound, tau = 0.17, 83.0, 0.25, 0.09176615913014215
    integral = quad(
        lambda value: np.exp(-0.5 * curvature * (value - rate) ** 2),
        -bound,
        bound,
        epsabs=1e-13,
    )[0]
    expected = -np.log(integral)
    assert np.isclose(
        bounded_laplace_adjustment([rate], [curvature], bound, tau), expected, atol=1e-11
    )


def test_unbounded_linear_gaussian_laplace_equals_exact_marginal_covariance():
    z = np.array([1.2, -0.7, 0.3])
    design = np.array([2.0, -1.0, 0.5])
    sigma, tau = 0.8, 0.3
    curvature = np.dot(design, design) / sigma**2 + 1 / tau**2
    rate = np.dot(design, z) / sigma**2 / curvature
    profile = (
        len(z) * np.log(sigma * np.sqrt(2 * np.pi))
        + np.log(tau * np.sqrt(2 * np.pi))
        + 0.5 * np.sum(((z - design * rate) / sigma) ** 2)
        + 0.5 * (rate / tau) ** 2
    )
    approximate = profile + bounded_laplace_adjustment(rate, curvature, 100.0, tau)
    covariance = sigma**2 * np.eye(len(z)) + tau**2 * np.outer(design, design)
    exact = 0.5 * (
        len(z) * np.log(2 * np.pi)
        + np.linalg.slogdet(covariance)[1]
        + z @ np.linalg.solve(covariance, z)
    )
    assert np.isclose(approximate, exact, atol=1e-12)


def test_laplace_fit_isolates_heldout_values():
    source, region, _ = _synthetic()
    original = LaplaceContrastOrbitData(**source.__dict__)
    poisoned = LaplaceContrastOrbitData(
        **{
            **source.__dict__,
            "y_hz": np.where(source.training, source.y_hz, source.y_hz + 1e7),
        }
    )
    config = LaplaceContrastOrbitConfig(measurement_sigma_hz=16, ar1_rho=0.8)
    a = fit_laplace_contrast_orbit(original, region, [0, 0], config)
    b = fit_laplace_contrast_orbit(poisoned, region, [0, 0], config)
    assert np.allclose(a.x_km, b.x_km, atol=1e-7)
    assert np.isclose(a.negative_log_posterior, b.negative_log_posterior)
    assert a.evaluation_rms_hz != b.evaluation_rms_hz
