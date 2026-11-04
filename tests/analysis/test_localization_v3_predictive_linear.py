import numpy as np
import pytest

from leo.analysis.localization_v3.history_position import make_problem
from leo.analysis.localization_v3.predictive_linear import (
    attach_predictive_linear,
    predictive_residual,
)
from tests.analysis.test_localization_v3_position import prepared


def test_predictive_residual_keeps_cross_curve_covariance():
    rng = np.random.default_rng(303)
    y, design = rng.normal(size=8), rng.normal(size=(8, 3))
    gram = np.eye(3)*2 + design.T@design
    sigma, groups = np.linspace(1., 2., 8), np.repeat([0, 1], 4)
    result = predictive_residual(y, design, gram, sigma, groups, bias_sigma=.3)
    same_curve = groups[:, None] == groups[None, :]
    covariance = np.diag(sigma**2) + design@np.linalg.solve(gram, design.T)+.3**2*same_curve
    expected = y@np.linalg.solve(covariance, y)+np.linalg.slogdet(covariance)[1]+8*np.log(2*np.pi)
    assert result['objective'] == pytest.approx(expected, abs=1e-12)
    assert np.any(covariance[:4, 4:] != 0)


def test_linear_evidence_changes_score_but_never_calibration_coefficients():
    scan, node = prepared()
    scan.previous_sources = {}
    scan.elements = {'99999': dict(provenance=dict(element_epoch_utc_ns=0))}
    p = make_problem(scan, node, np.ones(41, bool), 'c0', np.zeros(1), np.ones(1),
                     np.zeros(1), 1., None)
    x = np.zeros(2)
    curved = p.calculate(x)
    entry = dict(track_index=1, component='linear', candidate_index=0, norad=99999,
                 alias=0, points=21, observation_ids=scan.tracks[1]['observation_ids'])
    attach_predictive_linear(p, [entry], np.ones(1))
    joint = p.calculate(x)
    np.testing.assert_array_equal(joint['coefficient'], curved['coefficient'])
    np.testing.assert_array_equal(joint['noise_precision'], curved['noise_precision'])
    np.testing.assert_array_equal(joint['conditional_residual_hz'],
                                  curved['conditional_residual_hz'])
    assert joint['linear_calibration_coefficient_unchanged']
    assert joint['negative_twice_elbo'] == (
        curved['negative_twice_elbo']+joint['linear_predictive_objective'])
    assert joint['linear_raw_prediction_residual_hz'].shape == (21,)
    np.testing.assert_array_equal(p.curved_calculate(x)['coefficient'], curved['coefficient'])


def test_empty_linear_extension_keeps_original_problem():
    sentinel = object()
    assert attach_predictive_linear(sentinel, [], []) is sentinel
