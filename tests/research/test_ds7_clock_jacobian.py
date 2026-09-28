import numpy as np

from tools.ds7_clock_jacobian import drift_column


def test_physical_drift_uses_measurement_normalization():
    times = [10.0, 11.0, 13.0]
    canonical = drift_column(times, 0, 0, 10.94e9)
    physical = drift_column(times, 0, 0, 10.94e9, physical_baseband=True)
    np.testing.assert_allclose(physical, canonical * (11.2 / 10.94))
    assert abs(canonical.sum()) < 1e-12


def test_receiver_drift_does_not_leak_between_receivers():
    np.testing.assert_array_equal(drift_column([0.0, 1.0], 1, 0, 11.2e9), [0.0, 0.0])
