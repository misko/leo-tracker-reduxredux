import numpy as np
from diagnose_drift import line_values


def test_drift_line_uses_scan_midpoint_epoch_and_hz_units():
    np.testing.assert_array_equal(line_values([90000, 10], [0, 150, 300]), [88500, 90000, 91500])
