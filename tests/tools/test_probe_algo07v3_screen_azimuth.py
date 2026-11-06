"""The narrower projection preserves exact outputs and restores instrumentation."""

import numpy as np
import pytest
from probe_algo07v3_screen_azimuth import elevation_and_rate, operations, projection

from leo.analysis.localization_v3 import residual_screen
from leo.sky.frames import ecef_to_enu_matrix, geodetic_to_ecef_km, look_angles
from tests.analysis.test_orbit_phase_geometry import bank


def test_projection_bits_and_layout_including_coincident_observer():
    rng = np.random.default_rng(194718)
    for count in (0, 1, 19):
        position = rng.normal(size=(count, 37, 3)) * 7000
        velocity = rng.normal(size=position.shape) * 7
        for lat, lon in ((37.8, -122.5), (90., 180.), (-90., -180.)):
            observer, rotation = geodetic_to_ecef_km(lat, lon, 0.), ecef_to_enu_matrix(lat, lon)
            if count:
                position[0, 0] = observer
                velocity[0, 0] = [-0., 0., -0.]
            for p, v in ((position, velocity),
                         (np.asfortranarray(position), np.asfortranarray(velocity)),
                         (position[:, ::2], velocity[:, ::2])):
                before = (p.tobytes(), v.tobytes())
                _, elevation, _, rate = look_angles(p, v, observer, rotation)
                actual = elevation_and_rate(p, v, observer, rotation)
                for a, b in zip(actual, (elevation, rate), strict=True):
                    assert (a.shape, a.strides, a.dtype, a.tobytes()) == (
                        b.shape, b.strides, b.dtype, b.tobytes())
                assert before == (p.tobytes(), v.tobytes())


def test_complete_projection_wrapper_uses_original_phase_and_rf_math():
    functions, _ = operations()
    for times in ([], [0., 2.5, 1.25, 2.5]):
        for phase in (-2., 0., 3., [1.2, -0.3]):
            results = [f(bank(), times, [(37., -122.), (90., 180.)],
                         phase_seconds=phase, altitude_m=127., rf_hz=12.1e9)
                       for f in functions.values()]
            for a, b in zip(results[0], results[1], strict=True):
                assert all(x.tobytes() == y.tobytes() for x, y in zip(a, b, strict=True))


def test_projection_restores_after_failure():
    original = residual_screen.phase_frequency_grids
    with pytest.raises(RuntimeError), projection(lambda *args: None):
        raise RuntimeError('deliberate')
    assert residual_screen.phase_frequency_grids is original
