import numpy as np
import pytest
from scipy.stats import t
from fit_frequency import loss, fit, prepare_sessions


def test_normalized_likelihood_and_equal_scan_weight():
    r = np.array([[1., -20., 300.]])
    a = [(r, np.array([0.]), 5.)]
    b = [(2*r, np.array([0.]), 100.)]
    expected = -.5*(t.logpdf(r, 4, scale=100).mean()+t.logpdf(2*r, 4, scale=100).mean())
    assert loss(np.log([100., 4.]), {'a': a, 'b': b}) == pytest.approx(expected)


def test_rejects_test_sessions_and_incomplete_calibration():
    with pytest.raises(ValueError, match='unexpected'):
        prepare_sessions({'sessions': [{'session_id': 'test', 'candidate_rows': []}]}, {'cal'})
    with pytest.raises(ValueError, match='incomplete'):
        prepare_sessions({'sessions': []}, {'cal'})


def test_recovers_student_scale_without_changing_input():
    rng = np.random.default_rng(482)
    residual = 170*rng.standard_t(3., size=(1, 12000))
    sessions = {'cal': [(residual, np.array([0.]), 5.)]}
    result = fit(sessions)
    assert result['scale_hz'] == pytest.approx(170, rel=.08)
    assert result['degrees_of_freedom'] == pytest.approx(3., rel=.15)
    assert not result['at_bound']
