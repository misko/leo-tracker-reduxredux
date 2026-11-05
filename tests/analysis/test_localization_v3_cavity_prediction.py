import numpy as np
import pytest

from leo.analysis.localization_v3.cavity_prediction import (
    coarse_phase_scores,
    gaussian_prediction,
    legacy_phase_reference,
    unused_student_gap,
)
from leo.analysis.research.retained_track_likelihood import PERIOD


def test_phase_screen_matches_dense_covariance_after_whole_fragment_aliases():
    rng = np.random.default_rng(729)
    covariance = np.eye(8)+np.ones((8, 8))*.3
    frequency = rng.normal(size=(2, 8))
    frequency[1] += PERIOD
    derivative = rng.normal(size=(2, 8))
    values, mean, scales = rng.normal(size=8), rng.normal(size=8), np.array([.5, 2.])
    groups = np.repeat([0, 1], 4)
    result = coarse_phase_scores(values, mean, frequency, derivative, scales, covariance, groups)
    np.testing.assert_array_equal(result['aliases'], [[0, 0], [1, 1]])
    for j in range(2):
        raw = values-mean-frequency[j]+result['aliases'][j, groups]*PERIOD
        design = derivative[j]*scales[j]
        full = covariance+np.outer(design, design)
        expected = raw@np.linalg.solve(full, raw)+np.linalg.slogdet(full)[1]+8*np.log(2*np.pi)
        assert result['score'][j] == pytest.approx(expected, abs=1e-10)


def test_gaussian_prediction_keeps_correlated_prior_mean_update():
    y = np.array([2., -1., 3.])
    u = np.array([[1., 2.], [2., 1.], [0., 3.]])
    prior = np.array([[2., .5], [.5, 1.]])
    sigma = np.array([1., 2., 3.])
    result = gaussian_prediction(y, u, prior, sigma)
    full = np.diag(sigma**2)+u@prior@u.T
    expected = prior@u.T@np.linalg.solve(full, y)
    np.testing.assert_allclose(result['parameter_update'], expected, atol=1e-12)
    np.testing.assert_allclose(result['native_residual'], y-u@expected, atol=1e-12)
    objective = y@np.linalg.solve(full, y)+np.linalg.slogdet(full)[1]+3*np.log(2*np.pi)
    assert result['objective'] == pytest.approx(objective, abs=1e-12)


def test_legacy_reference_replays_round_inputs_not_final_posterior():
    history = [dict(fit=dict(parameters=[v])) for v in [1., 2., 100.]]
    result = legacy_phase_reference(history, [0.], lambda ref, x: ref+x)
    np.testing.assert_array_equal(result, [3.])
    with pytest.raises(ValueError, match='recorded'):
        legacy_phase_reference(history[:1], [0.], lambda ref,x: ref+x)
    assert unused_student_gap(None) == 0.
    assert 0 < unused_student_gap(30.) < unused_student_gap(4.)
