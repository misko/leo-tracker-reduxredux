"""Screen projections preserve the full sky helper's elevation and rate bits."""

import numpy as np
import pytest

from leo.analysis.localization_v3 import screen_geometry
from leo.sky.frames import ecef_to_enu_matrix, geodetic_to_ecef_km, look_angles


@pytest.mark.parametrize('count', [0, 1, 19])
@pytest.mark.parametrize('layout', ['C', 'F', 'strided'])
@pytest.mark.parametrize('site', [(37.8, -122.5), (90., 180.), (-90., -180.)])
def test_projection_values_layout_and_input_preservation(count, layout, site):
    rng = np.random.default_rng(194718)
    position = rng.normal(size=(count, 37, 3)) * 7000
    velocity = rng.normal(size=position.shape) * 7
    observer = geodetic_to_ecef_km(*site, 127.)
    rotation = ecef_to_enu_matrix(*site)
    if count:
        position[0, 0] = observer
        position[0, 2] = observer + rotation[2] * 700
        position[0, 4] = observer - rotation[2] * 700
        velocity[0, :5] = [-0., 0., -0.]
    if layout == 'F':
        position, velocity = np.asfortranarray(position), np.asfortranarray(velocity)
    elif layout == 'strided':
        position, velocity = position[:, ::2], velocity[:, ::2]
    inputs = position, velocity, observer, rotation
    before = [a.tobytes() for a in inputs]
    _, elevation, _, rate = look_angles(*inputs)
    actual = screen_geometry._elevation_and_rate(*inputs)
    for a, b in zip(actual, (elevation, rate), strict=True):
        assert (a.shape, a.strides, a.dtype, a.tobytes()) == (
            b.shape, b.strides, b.dtype, b.tobytes())
    assert before == [a.tobytes() for a in inputs]
