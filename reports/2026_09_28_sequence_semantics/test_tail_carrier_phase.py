import numpy as np
from tail_carrier_phase import estimate_gain


def test_gain_recovery_ignores_later_evaluation_samples():
    signs = np.tile([1, -1], 50)
    gain = 0.3 + 0.8j
    values = gain * signs
    np.testing.assert_allclose(estimate_gain(values, signs), gain)
    values[30:] = 1000j
    np.testing.assert_allclose(estimate_gain(values, signs), gain)
