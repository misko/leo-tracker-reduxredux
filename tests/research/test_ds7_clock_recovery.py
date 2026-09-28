import numpy as np

from tools.ds7_clock_recovery import drift_column, profiled_single_loglike_gradient


def test_zero_drift_leaves_observations_unchanged() -> None:
    track = {"times_s": [1.0, 2.0, 4.0], "rf_hz": 11_440_000_000.0}
    values = np.asarray([10.0, 20.0, 30.0])

    np.testing.assert_array_equal(values + 0.0 * drift_column(track), values)
    assert abs(float(np.mean(drift_column(track)))) < 1e-15


def test_profiled_slope_gradient_matches_finite_difference() -> None:
    times = np.linspace(-2.0, 2.0, 11)
    column = times - np.mean(times)
    prediction = 100.0 + 3.0 * times
    y = prediction + 17.0 + 0.4 * column + np.sin(times) * 2.0
    mask = np.ones(len(times), dtype=bool)
    slope = -0.2

    _, gradient = profiled_single_loglike_gradient(y, prediction, mask, column, slope)
    step = 1e-5
    plus = profiled_single_loglike_gradient(y, prediction, mask, column, slope + step)[0]
    minus = profiled_single_loglike_gradient(y, prediction, mask, column, slope - step)[0]

    assert abs(gradient - (plus - minus) / (2 * step)) < 1e-6
