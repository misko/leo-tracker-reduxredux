from importlib import import_module

import numpy as np
import pytest

study = import_module("reports.ALGO08.single-core-2x.mirrored_yaw_trial")


def circular_states(times, inclinations):
    angle = np.asarray(times)
    cos_i, sin_i = (f(np.deg2rad(inclinations))[:, None] for f in (np.cos, np.sin))
    position = np.stack((np.broadcast_to(np.cos(angle), (len(inclinations), angle.shape[-1])),
                         cos_i * np.sin(angle), sin_i * np.sin(angle)), axis=-1)
    velocity = np.stack((np.broadcast_to(-np.sin(angle), position.shape[:-1]),
                         cos_i * np.cos(angle), sin_i * np.cos(angle)), axis=-1)
    return np.stack((position, velocity), axis=2)


def test_yaw_profile_separates_inclined_orbits_and_rejects_equatorial_gauge():
    angles = np.array([.2, .5, .9])
    base = circular_states(angles, [0., 53., 98.])
    phase = np.stack((base[:, :, 1], -base[:, :, 0]), axis=2)
    yaw = np.cross([0., 0., 1.], base)
    shared = 4.2e-5
    individual = np.array([.012, -.004, .005])[:, None, None, None]
    corrected = base + shared * yaw + individual * phase
    estimated, leverage, _, _ = study.profiled_yaw(base, corrected, phase)
    assert np.isnan(estimated[0]) and leverage[0] < study.MIN_LEVERAGE
    np.testing.assert_allclose(estimated[1:], shared, atol=1e-16)
    assert min(leverage[1:]) > .5


def test_orbit_plane_rotation_ignores_per_satellite_change_in_argument():
    angles = np.array([.2, .5, .9])
    base = circular_states(angles, [42., 53.])
    offset = circular_states(angles + np.array([.24, -.42])[:, None], [42., 53.])
    yaw = .0012
    c, s = np.cos(yaw), np.sin(yaw)
    rotate = np.array([[c, -s, 0.], [s, c, 0.], [0., 0., 1.]])
    np.testing.assert_allclose(study.plane_yaw(base, offset @ rotate.T), [yaw, yaw], atol=1e-15)


@pytest.mark.parametrize("held, qualified", [([3., 2.5], True), ([-3., 2.5], False),
                                            ([.8, 3.], False)])
def test_rate_requires_both_history_holdbacks_to_improve(held, qualified):
    rows = [dict(common_yaw_arcsec=x, elapsed_hours=2.) for x in (2., 2., *held)]
    forecast = study.rate_forecast(rows)
    assert forecast["qualified"] is qualified
    assert forecast["training_rate_arcsec_per_hour"] == 1.


def test_required_yaw_is_larger_further_from_the_equator():
    assert study.required_yaw(48.) > study.required_yaw(-33.) > study.required_yaw(0.)
