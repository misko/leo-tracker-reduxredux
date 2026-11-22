from importlib import import_module

import numpy as np
import pytest

from leo.analysis.research import continuous_curve_fit, orbit_uncertainty
from leo.sky.frames import geodetic_to_ecef_km


trial = import_module("reports.ALGO08.single-core-2x.mirrored_height_trial")


def test_observer_height_reaches_both_geometry_ports_and_restores_them():
    coordinate = (-36., 145.)
    expected = geodetic_to_ecef_km(*coordinate, 100.)
    with pytest.raises(ValueError, match="zero-height components"):
        with trial.observer_height(100.):
            np.testing.assert_array_equal(continuous_curve_fit.geodetic_to_ecef_km(*coordinate, 0.), expected)
            np.testing.assert_array_equal(orbit_uncertainty.geodetic_to_ecef_km(*coordinate, 0.), expected)
            orbit_uncertainty.geodetic_to_ecef_km(*coordinate, 12.)
    assert continuous_curve_fit.geodetic_to_ecef_km is geodetic_to_ecef_km
    assert orbit_uncertainty.geodetic_to_ecef_km is geodetic_to_ecef_km


def test_projection_cancels_baseline_gradient_and_recovers_known_height_response():
    coordinate = (52., 12.)
    observer = geodetic_to_ecef_km(*coordinate, 0.)
    center = np.array([.2, -.5])
    response_per_km = np.array([.6, -.4])
    curvature = np.array([[4., 1.], [1., 3.]])

    def loss(position):
        raised = continuous_curve_fit.geodetic_to_ecef_km(*coordinate, 0.)
        height_km = np.linalg.norm(raised - observer)
        residual = position - center - height_km * response_per_km
        return residual @ curvature @ residual

    result = trial.projections(loss, np.array([.27, -.61]))
    for step, row in result.items():
        assert step in trial.STEPS_KM
        assert np.linalg.norm(row["zero_gradient"]) > 0
        for height in trial.HEIGHTS_M:
            np.testing.assert_allclose(row["shift_km"][height], response_per_km * height / 1000., atol=1e-11)
