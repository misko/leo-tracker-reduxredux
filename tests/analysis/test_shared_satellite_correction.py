import numpy as np

from leo.analysis.research.shared_satellite_correction import (
    PERIOD_HZ,
    profile_curve,
    ridge_shared_fit,
    soft_curve_responsibilities,
)


def test_one_native_alias_is_profiled_for_entire_curve():
    t = np.linspace(-1, 1, 30)
    predicted = 10000 * t**2
    observed = predicted - PERIOD_HZ + 321
    out = profile_curve(observed, predicted)
    assert out["aliases"].tolist() == [1]
    assert abs(out["bias"][0] - 321) < 1
    assert out["rms"][0] < 1


def test_linear_curve_cannot_change_shared_coefficients():
    t = np.linspace(-1, 1, 40)
    x = np.column_stack([t, t**2])
    truth = np.array([12.0, 35.0])
    covariance = np.eye(2) * 1e12
    first, _, count = ridge_shared_fit([x], [x @ truth], [1], covariance, [True])
    second, _, other_count = ridge_shared_fit(
        [x, x], [x @ truth, 1e8 * t], [1, 1], covariance, [True, False]
    )
    np.testing.assert_allclose(first, truth, atol=1e-4)
    np.testing.assert_array_equal(first, second)
    assert count == other_count == 40


def test_prior_regularizes_an_unobserved_shared_direction():
    t = np.linspace(-1, 1, 30)
    x = np.column_stack([t, np.zeros_like(t)])
    theta, _, _ = ridge_shared_fit([x], [50 * t], [1], np.diag([1e8, 0.1]), [True])
    assert abs(theta[0] - 50) < 0.01
    assert theta[1] == 0


def test_satellite_prior_is_charged_once_for_multiple_curves():
    t = np.linspace(-1, 1, 20)
    x = t[:, None]
    prior = np.array([[4.0]])
    theta, information, _ = ridge_shared_fit([x, x], [10 * t, 10 * t], [1, 1], prior, [True, True])
    expected = 10 * (2 * (t @ t)) / (2 * (t @ t) + 150**2 / 4)
    np.testing.assert_allclose(theta[0], expected, rtol=1e-12)
    np.testing.assert_allclose(information[0, 0], 2 * (t @ t), rtol=1e-12)


def test_signal_clutter_mass_accounts_for_all_hypotheses():
    signal, clutter = soft_curve_responsibilities(
        [150**2, 1e10], [150, 1e5], [0, 0], [True, True], 30
    )
    np.testing.assert_allclose(signal.sum() + clutter, 1)
    assert signal[0] > 0.99 and signal[1] == 0
    signal, clutter = soft_curve_responsibilities([1e10], [1e5], [0], [False], 30)
    assert signal[0] == 0 and clutter == 1
