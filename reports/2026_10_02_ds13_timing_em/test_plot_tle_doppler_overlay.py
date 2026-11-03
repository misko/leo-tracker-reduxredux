from types import SimpleNamespace

import numpy as np
import pytest
from joint_inputs import _coordinates, _ecef
from plot_tle_doppler_overlay import CARRIER_HZ, calibrated_points, orbital_curve
from prediction_jacobian import paired_prediction_jacobian


def synthetic():
    nodes = np.arange(-2, 5, 0.25)
    observer = _ecef(*_coordinates([0.0, 0.0]))
    position = observer + np.column_stack([
        np.full(len(nodes), 600.0), 7.0 * nodes, np.full(len(nodes), 100.0)])
    return SimpleNamespace(numbers=np.array([1]), nodes=nodes, position=position[None],
                           velocity=np.broadcast_to([0.0, 7.0, 0.0], (1, len(nodes), 3)),
                           times=np.array([0.0, 1.0, 2.0]),
                           rf=np.array([10.7e9, 11.2e9, 11.5e9]),
                           receiver=np.array([0, 1, 0]), reference_time_s=150.0)


def test_physical_dense_path_matches_corrected_channel_switched_prediction():
    data = synthetic()
    parameters = np.array([0.0, 0.0, 1200.0, 2.0, -400.0, -1.0, 0.5])
    original = parameters.copy()
    predicted, _, _ = paired_prediction_jacobian(data, parameters, np.arange(3), np.zeros(3, int))
    dense, _ = orbital_curve(data, parameters, [0], data.times)
    receiver = data.receiver
    line = parameters[2 + 2 * receiver] + parameters[3 + 2 * receiver] * (data.times - 150)
    np.testing.assert_allclose(dense[:, 0], (predicted - line) * CARRIER_HZ / data.rf,
                               rtol=0, atol=1e-8)
    np.testing.assert_array_equal(parameters, original)


def test_alias_assignment_removes_calibration_and_preserves_small_residual():
    alias = 227272.72727272727
    prediction = np.array([[120000.0], [-150000.0]])
    rf = np.array([10.7e9, 11.5e9])
    nuisance = np.array([2000.0, -3000.0])
    measured = prediction[:, 0] + np.array([100.0, -70.0]) + alias * np.array([3, -4])
    result = calibrated_points(measured, prediction, rf, nuisance, alias)
    np.testing.assert_allclose(result["residual_hz"][:, 0], [100 * CARRIER_HZ / rf[0],
                                                             -70 * CARRIER_HZ / rf[1]])
    np.testing.assert_allclose(result["doppler_hz"] - result["modeled_doppler_hz"],
                               result["residual_hz"], atol=1e-8)
    np.testing.assert_array_equal(result["alias_integer"][:, 0], [-3, 4])


def test_dense_curve_covers_full_requested_range_and_respects_ephemeris():
    data = synthetic()
    parameters = np.zeros(7)
    curve, _ = orbital_curve(data, parameters, [0], np.arange(0, 3.25, 0.25))
    assert curve.shape == (13, 1)
    assert np.all(np.isfinite(curve))
    with pytest.raises(ValueError, match="ephemeris"):
        orbital_curve(data, parameters, [0], [10.0])
