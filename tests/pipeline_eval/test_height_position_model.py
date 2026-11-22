from importlib import import_module

import numpy as np
import pytest

from leo.analysis.localization_v3.region import SearchRegion
from leo.sky.frames import geodetic_to_ecef_km


model = import_module("reports.ALGO08.single-core-2x.height_position_model")
trial = import_module("reports.ALGO08.single-core-2x.height_position_trial")


def test_split_uses_whole_orbits_and_preserves_both_receivers():
    receivers = np.arange(8) % 2
    training = trial.groups(receivers, 3, np.random.default_rng(3))
    assert training.sum() == 5
    assert set(receivers[training]) == set(receivers[~training]) == {0, 1}
    assert np.array_equal(training, trial.groups(receivers, 3, np.random.default_rng(3)))


def test_held_shape_contrasts_remove_affines_without_shared_coefficients():
    times = np.array([[0., 5., 17., 44.], [7., 13., 22., 30.]])
    curvature = times ** 2
    affine = np.array([100., -404.])[:, None] + times * np.array([8., -11.])[:, None]
    clean = model.affine_residual(curvature[..., None], times)
    shifted = model.affine_residual((curvature + affine)[..., None], times)
    np.testing.assert_allclose(shifted, clean, atol=1e-10)
    assert np.linalg.norm(clean) > 0


@pytest.fixture
def geometry():
    region = SearchRegion((-17., 148.))
    rng = np.random.default_rng(34)
    tracks, points = 8, 12
    times = np.broadcast_to(np.linspace(0, 200, points), (tracks, points))
    observer = geodetic_to_ecef_km(*region.center, 0)
    offset = rng.uniform(-1200., 1200., (tracks, points, 3))
    velocity = rng.normal(0., 4., (tracks, points, 3))
    phase = model.PHASE_STEP_S * velocity
    geometry = model.Geometry(observer + np.stack([offset, offset + phase, offset - phase]),
                              np.broadcast_to(velocity, (3, tracks, points, 3)), times,
                              np.arange(tracks) % 2, np.linspace(10.7e9, 12.65e9, tracks))
    return region, geometry


def test_linear_height_agrees_with_exact_vertical_finite_difference(geometry):
    region, model_geometry = geometry
    point = np.array([3., -4., .001])
    exact, _ = model_geometry.mean_and_phase(region, point, exact_height=True)
    linear, _ = model_geometry.mean_and_phase(region, point)
    np.testing.assert_allclose(linear, exact, rtol=0, atol=1e-4)


@pytest.mark.parametrize("fitted_c", [False, True])
def test_planted_height_and_no_held_frequency_dependence(geometry, fitted_c):
    region, model_geometry = geometry
    truth = [6., -4., 2.]
    data, _ = model_geometry.mean_and_phase(region, truth, exact_height=True)
    training = np.array([True] * 5 + [False] * 3)
    free = model.fit(region, model_geometry, data, training, fit_height=True, fitted_c=fitted_c)
    zero = model.fit(region, model_geometry, data, training, fit_height=False, fitted_c=fitted_c)
    assert free["success"] and zero["success"]
    np.testing.assert_allclose(free["position_km"], truth, atol=.1)
    assert free["held_shape_rms_hz"] < zero["held_shape_rms_hz"]
    changed = data.copy()
    changed[~training] += 11 * model_geometry.times[~training] ** 2
    held = model.fit(region, model_geometry, changed, training, fit_height=True, fitted_c=fitted_c)
    assert held["position_km"] == free["position_km"]
    assert held["held_shape_rms_hz"] > free["held_shape_rms_hz"]
