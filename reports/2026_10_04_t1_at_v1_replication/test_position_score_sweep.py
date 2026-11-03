from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest

from position_score_sweep import BASE, SPECS, Objective, validate_spec, summarize


def test_sixteen_unique_new_settings_and_two_controls():
    assert len(SPECS) == 18
    assert len({tuple(s.values()) for s in SPECS.values()}) == 18
    for s in SPECS.values(): validate_spec(s, 20)
    assert SPECS['C0']['relative_sigma_s'] == 1.
    assert SPECS['C1']['relative_sigma_s'] == 1./3.
    assert SPECS['V05']['detection_budget'] > 1  # budget, not per-satellite probability


@pytest.mark.parametrize('key', list(BASE))
@pytest.mark.parametrize('value', [0., -1., np.nan, np.inf])
def test_invalid_hyperparameters(key, value):
    with pytest.raises(ValueError): validate_spec(dict(BASE, **{key:value}), 20)


def test_detection_probability_must_be_valid():
    with pytest.raises(ValueError): validate_spec(SPECS['V05'], 1)


@pytest.mark.parametrize('sigma', [75., 125., 200., 300.])
def test_rf_fisher_cross_and_diagonal_use_configured_noise(sigma):
    # Isolate the block that the legacy implementation hardcoded to 200 Hz.
    obj=object.__new__(Objective);obj.size=8
    probs=np.array([[.8,.1],[.2,.6],[.1,.4]])
    visible=np.ones_like(probs,dtype=bool)
    physical=np.arange(6*8,dtype=float).reshape(6,8)/100
    jac=SimpleNamespace(transpose_multiply=lambda w:physical.T@w)
    prior=np.diag([0.,0.,0.,0.,0.,0.,.01,9.])
    obj.base=SimpleNamespace(sigma_hz=sigma,last={},
        predict=lambda v,with_jacobian:(None,None,jac),
        penalty_curvature=lambda v:prior,
        vector_gradient=lambda p,v:p)
    obj.likelihood=SimpleNamespace(last_result={'row_association_probability':probs})
    obj.features=np.array([[-.3],[.1],[.2]])
    legacy=np.eye(8);legacy[6,6]+=.01;legacy[7,7]+=1.
    with patch('position_score_sweep._fisher_system',return_value=(legacy,visible)):
        result=obj.curvature(np.zeros(9))
    weights=probs/sigma**2
    cross=physical.T@(weights*obj.features[:,0,None]).ravel()
    np.testing.assert_allclose(result[:8,8],cross)
    np.testing.assert_allclose(result[8,:8],cross)
    np.testing.assert_allclose(result[8,8],float((obj.features.T@(weights.sum(axis=1)[:,None]*obj.features))[0,0]))
    np.testing.assert_allclose(result[:8,:8],np.eye(8)+prior)


def test_summary_does_not_confuse_better_rms_with_position_improvement():
    rows=[]
    for mode,error,rms in [('C1',500.,100.),('V01',1500.,20.)]:
        for scan in ['N01','N02']:
            rows.append(dict(scan=scan,arm='fitted-c',mode=mode,distance_m=error,
                converged=True,boundary=False,owner_rms_hz=rms,
                posterior_weighted_residual_rms_hz=rms,mean_signal_posterior=.9,
                common_reference_data_nll=100.))
    result=next(r for r in summarize(rows) if r['mode']=='V01')
    assert result['worsened_vs_C1']==2 and result['below_1km']==0
    assert result['median_posterior_rms_hz']==20.


def test_single_candidate_detection_clutter_tradeoff_when_visibility_is_fixed():
    from finite_set_likelihood import prepare_finite_set_likelihood
    prepared=prepare_finite_set_likelihood(np.array([0., 100., 1000.]),np.arange(3))
    predicted=np.array([[20.,400.],[130.,400.],[1500.,500.]])
    visible=np.ones_like(predicted,dtype=bool)
    q1,q2,lam1=.04,.01,2.
    lam2=lam1*(q2/(1-q2))/(q1/(1-q1))
    first=prepared.evaluate(predicted,visible,sigma_hz=200.,detection_probability=q1,
                            clutter_rate=lam1,return_gradient=True)
    second=prepared.evaluate(predicted,visible,sigma_hz=200.,detection_probability=q2,
                             clutter_rate=lam2,return_gradient=True)
    # One observed candidate per group: preserving detection odds / clutter
    # preserves responsibilities and frequency gradients, not raw NLL constants.
    np.testing.assert_allclose(first['row_association_probability'],second['row_association_probability'],atol=1e-12)
    np.testing.assert_allclose(first['prediction_gradient'],second['prediction_gradient'],atol=1e-12)
    assert abs(first['total_log_likelihood']-second['total_log_likelihood'])>1e-5
