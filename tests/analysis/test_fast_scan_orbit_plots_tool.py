from types import SimpleNamespace

import numpy as np
import pytest

from tools.fast_scan_orbit_plots import receiver_nuisance


def test_published_receiver_calibration_uses_receive_time_and_original_rf_center():
    obs = SimpleNamespace(
        times_s=np.array([0.0, 50.0, 100.0, 150.0]),
        time_center_s=75.0,
        receiver=np.array([0, 1, 0, 1]),
        rf_hz=np.array([10e9, 12e9, 12e9, 10e9]),
        rf_center_hz=11e9,
    )
    state = SimpleNamespace(
        vector=[0, 0, 10, 2, 20, 3, 5],
        receiver_baseline_hz=[100, 200, 300, 400],
        clock_nodes_s=[0, 150],
        clock_knots_hz=[[0, 30], [30, 0]],
        rf_time_coefficients=[4, 8],
    )
    expected = [
        100 + 10 - 150 - 5 + 0 + 3,
        200 + 20 - 75 + 5 + 20 - 2,
        300 + 10 + 50 + 5 + 20 + 1,
        400 + 20 + 225 - 5 + 0 - 6,
    ]
    np.testing.assert_allclose(receiver_nuisance(state, obs), expected)
    state.receiver_baseline_hz = [0]
    with pytest.raises(ValueError, match="inventory differs"):
        receiver_nuisance(state, obs)
