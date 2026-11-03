from pathlib import Path
from types import SimpleNamespace
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'tools'))
from ds23_joint_probe_calibration import conditional_block, curved_entries


def test_joint_conditional_normal_equations_equal_correlated_Gaussian():
    values = np.array([31., 39.])
    features = np.array([[1., 0.], [2., 3.]])
    intercept = np.array([4., -3.])
    variance, kappa = 100., .9
    covariance = variance*np.array([[1., kappa], [kappa, 1.]])
    conditional_values, conditional_design, conditional_mean = conditional_block(
        values[1:], features[1:], intercept[1:], values[:1], features[:1], intercept[:1], [0], kappa)
    design = np.vstack((features[0]/np.sqrt(variance), conditional_design/np.sqrt(variance*(1-kappa*kappa))))
    response = np.r_[(values[0]-intercept[0])/np.sqrt(variance),
                     (conditional_values-conditional_mean)/np.sqrt(variance*(1-kappa*kappa))]
    precision = np.eye(2)+design.T@design
    expected = np.eye(2)+features.T@np.linalg.solve(covariance, features)
    np.testing.assert_allclose(precision, expected, rtol=0, atol=1e-14)
    coefficient = np.linalg.solve(precision, design.T@response)
    exact = np.linalg.solve(expected, features.T@np.linalg.solve(covariance, values-intercept))
    np.testing.assert_allclose(coefficient, exact, rtol=0, atol=1e-14)


def test_linear_secondary_never_enters_calibration_while_curved_evidence_can():
    times = np.linspace(0, 60, 41)
    noise = np.random.default_rng(23).normal(0, 15, len(times))
    tracks = [dict(times=times, values=1000+20*times+noise),
              dict(times=times, values=1000+20*times+2000*((times-30)/30)**2+noise)]
    entries = [dict(component='linear', track_index=0), dict(component='curved', track_index=1)]
    curved, linear, _ = curved_entries(SimpleNamespace(tracks=tracks), entries, dict(marginal_sigma_hz=50.))
    assert [r['component'] for r in curved] == ['curved']
    assert [r['component'] for r in linear] == ['linear']


def test_joint_transformation_rejects_invalid_covariance_or_misaligned_anchors():
    for kappa in (-.1, 1., np.nan):
        with pytest.raises(ValueError):
            conditional_block([2.], [[1.]], [0.], [1.], [[1.]], [0.], [0], kappa)
    with pytest.raises(ValueError, match='aligned'):
        conditional_block([2.], [[1.]], [0.], [1.], [[1.]], [0.], [0, 0], .9)
