import runpy
from pathlib import Path

import numpy as np

from leo.sky.frames import EARTH_ROTATION_RATE_RAD_S, teme_to_ecef

api = runpy.run_path(str(Path(__file__).with_name("phase.py")))


def test_zero_exact_and_common_relative_derivatives():
    p = np.array([6900.0, 400.0, 1800.0])
    sec = np.array([1.0, 7.0, -2.0])
    np.testing.assert_array_equal(api["transformed"](p, sec, 0)[0], p)
    t = 0.7
    h = 1e-4
    _, common, relative = api["transformed"](p, sec, t)
    common_fd = (
        api["transformed"](p + h * sec, sec, t)[0] - api["transformed"](p - h * sec, sec, t)[0]
    ) / (2 * h)
    relative_fd = (
        api["transformed"](p + h * sec, sec, t + h)[0]
        - api["transformed"](p - h * sec, sec, t - h)[0]
    ) / (2 * h)
    np.testing.assert_allclose(common, common_fd, atol=1e-8, rtol=0)
    np.testing.assert_allclose(relative, relative_fd, atol=1e-8, rtol=0)


def test_actual_frame_sign_and_rigid_rotation_identity():
    p = np.array([6900.0, 400.0, 1800.0])
    v = np.array([1.0, 7.0, -2.0])
    angle = 0.4
    shift = 10.0
    shifted = teme_to_ecef(p, v, angle + EARTH_ROTATION_RATE_RAD_S * shift)
    target = teme_to_ecef(p, v, angle)
    for actual, expected in zip(shifted, target, strict=True):
        np.testing.assert_allclose(
            api["rotate"](actual, EARTH_ROTATION_RATE_RAD_S * shift), expected, atol=1e-12, rtol=0
        )


def test_spatial_site_chain_off_equator():
    p = np.array([6900.0, 400.0, 1800.0])
    v = np.array([1.0, 7.0, -2.0])
    site = np.array([4000.0, 1000.0, 4500.0])
    jac = np.array([[0.0, 1.0, 0.0], [0.7, 0.0, -0.6]])
    _, gradient = api["radial"](p, v, site, jac)
    h = 1e-3
    for i in range(2):
        fd = (
            api["radial"](p, v, site + h * jac[i], jac)[0]
            - api["radial"](p, v, site - h * jac[i], jac)[0]
        ) / (2 * h)
        np.testing.assert_allclose(gradient[i], fd, atol=1e-10, rtol=0)
