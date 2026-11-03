import numpy as np
import pytest

from leo.analysis.research.predictive_track_gate import predictive_track_gate


def test_supported_calibration_trend_is_distinguished_from_unexplained_trend():
    times = np.linspace(0., 14., 21)
    x = times-times.mean()
    residual = 14.*x
    no_uncertainty = predictive_track_gate(residual, np.zeros((len(x), 1)), np.eye(1), 75., times)
    calibration_uncertainty = predictive_track_gate(residual, (8.*x)[:, None], np.eye(1), 75., times)
    assert not no_uncertainty['compatible']
    assert calibration_uncertainty['compatible']


def test_prediction_is_invariant_under_orthogonal_calibration_coordinates():
    rng = np.random.default_rng(8051)
    u = rng.normal(size=(18, 3))*50
    a = rng.normal(size=(3, 3))
    precision = a.T@a + np.eye(3)
    q, _ = np.linalg.qr(rng.normal(size=(3, 3)))
    raw = rng.normal(size=18)*50
    first = predictive_track_gate(raw, u, precision, 75., np.arange(18))
    second = predictive_track_gate(raw, u@q, q.T@precision@q, 75., np.arange(18))
    np.testing.assert_allclose(first['whitened_innovations_hz'], second['whitened_innovations_hz'], atol=1e-10)


def test_linear_calibration_uncertainty_does_not_hide_an_abrupt_jump():
    times = np.arange(80.)
    x = times-times.mean()
    residual = np.where(times < 40, -200., 200.)
    gate = predictive_track_gate(residual, (8.*x)[:, None], np.eye(1), 75., times)
    assert not gate['compatible']


@pytest.mark.parametrize('sigma, times', [(0., np.arange(8)), (75., np.zeros(8))])
def test_invalid_measurements_are_rejected(sigma, times):
    with pytest.raises(ValueError):
        predictive_track_gate(np.zeros(8), np.ones((8, 1)), np.eye(1), sigma, times)
