import importlib.util
from pathlib import Path

import numpy as np
import pytest

spec = importlib.util.spec_from_file_location('support_position_test', Path(__file__).with_name('run.py'))
run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run)


@pytest.mark.parametrize('tau', [-4.995, -.0001, .25, 4.995])
def test_each_observation_matches_scalar_original_interpolation(tau):
    rng = np.random.default_rng(37)
    grid = np.arange(-5., 5.01, .25)
    config = dict(geographic_prior_center_deg=[37., -122.], timing_grid_s=grid)
    position = rng.normal(size=(3, len(grid), 4, 3))*100 + np.array([7000., 1000., 2000.])
    track = dict(candidate_position_km=position, candidate_velocity_km_s=rng.normal(size=position.shape),
                 mask=np.array([True, False, True, True]),
                 nominal_support_shift_s=np.array([-.0042, 0., -.0036, -.0046]))
    doc = dict(tracks=[track])
    original = run.OriginalStationary(doc, config)
    changed = run.SupportStationary(doc, config)
    x = np.array([.2, -.3, tau])
    prediction, visible = changed.prediction(track, x)
    expected = np.empty_like(prediction)
    for i, shift in enumerate(track['nominal_support_shift_s']):
        point = x.copy(); point[2] += shift
        expected[:, i] = original.prediction(track, point)[0][:, i]
    np.testing.assert_allclose(prediction, expected, rtol=0, atol=1e-9)
    np.testing.assert_array_equal(prediction[:, 1], original.prediction(track, x)[0][:, 1])
    with pytest.raises(ValueError):
        changed.prediction(track, np.array([0., 0., -5.]))


def test_shifts_and_frequency_changes_remain_training_only():
    track = dict(track_id='t', y=np.array([10., 20.]), mask=np.array([True, False]),
                 times_s=np.array([1., 2.]), visits=[1, 2])
    row = dict(track_id='t', observation_index=0, time_s=1., visit=1,
               measured_hz=10., delta_hz=3., nominal_support_shift_s=-.004)
    result = run.patch_documents([dict(tracks=[track])], [row])[0]['tracks'][0]
    np.testing.assert_array_equal(result['y'], [13., 20.])
    np.testing.assert_array_equal(result['nominal_support_shift_s'], [-.004, 0.])
    np.testing.assert_array_equal(track['y'], [10., 20.])
    assert 'nominal_support_shift_s' not in track
    with pytest.raises(AssertionError):
        run.patch_documents([dict(tracks=[track])], [dict(row, observation_index=1)])
