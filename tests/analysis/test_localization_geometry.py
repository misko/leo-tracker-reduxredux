import numpy as np
import pytest

from leo.analysis.localization_geometry import stationary_range_rate_grid


def test_dot_product_geometry_matches_explicit_line_of_sight():
    rng = np.random.default_rng(436)
    up = rng.normal(size=(32, 3))
    up /= np.linalg.norm(up, axis=1, keepdims=True)
    receivers = up*6371.
    positions = rng.normal(size=(17, 12, 3))
    positions *= 6921./np.linalg.norm(positions, axis=2, keepdims=True)
    velocities = rng.normal(size=positions.shape)*4
    line = positions[None]-receivers[:, None, None]
    unit = line/np.linalg.norm(line, axis=-1, keepdims=True)
    expected_rate = np.sum(velocities[None]*unit, axis=-1)
    expected_elevation = np.einsum('pstc,pc->pst', unit, up)
    rate, elevation = stationary_range_rate_grid(positions, velocities, receivers, up)
    np.testing.assert_allclose(rate, expected_rate, rtol=1e-11, atol=1e-11)
    np.testing.assert_allclose(elevation, expected_elevation, rtol=1e-11, atol=1e-11)


def test_overhead_and_radial_velocity():
    rate, elevation = stationary_range_rate_grid(
        np.array([[[6921., 0., 0.]]]), np.array([[[2., 7., 0.]]]),
        np.array([[6371., 0., 0.]]), np.array([[1., 0., 0.]]),
    )
    assert rate.item() == pytest.approx(2.)
    assert elevation.item() == pytest.approx(1.)


def test_zero_range_and_nonunit_up_rejected():
    with pytest.raises(ValueError):
        stationary_range_rate_grid(np.ones((1, 1, 3)), np.zeros((1, 1, 3)),
                                   np.ones((1, 3)), np.array([[1., 0., 0.]]))
    with pytest.raises(ValueError):
        stationary_range_rate_grid(np.ones((1, 1, 3)), np.zeros((1, 1, 3)),
                                   np.zeros((1, 3)), np.array([[2., 0., 0.]]))
