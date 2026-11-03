from types import SimpleNamespace

import numpy as np
import pytest
from scipy.integrate import quad

from position_structure_study import (ALIAS, MODES, Objective, SingleWindowLikelihood,
                                      density_terms, row_weights)


def data():
    return SimpleNamespace(times=np.array([0.,1.,2.,6.,9.,11.]),
        owners=np.array([10,10,10,10,20,20]),receiver=np.array([0,0,1,1,0,0]),
        margin=np.array([.01,.02,.03,.04,.4,2.]),
        measured=np.array([0.,100.,300.,1000.,2000.,3000.]),
        group=np.arange(6),numbers=np.array([10,20]))


def test_ten_new_approaches_and_reference():
    assert len(MODES)==11
    assert set(MODES)=={'C1',*(f'A{i:02}' for i in range(1,11))}


@pytest.mark.parametrize('mode',MODES)
def test_all_weights_positive_and_total_information_scale_preserved(mode):
    w=row_weights(data(),mode)
    assert np.all(np.isfinite(w)) and np.all(w>0)
    assert w.mean()==pytest.approx(1.)


def test_satellite_and_receiver_balancing():
    d=data();w=row_weights(d,'A01')
    assert w[d.owners==10].sum()==pytest.approx(w[d.owners==20].sum())
    w=row_weights(d,'A02')
    totals=[w[(d.owners==sat)&(d.receiver==rx)].sum() for sat,rx in [(10,0),(10,1),(20,0)]]
    np.testing.assert_allclose(totals,np.repeat(2.,3))


def test_time_weighting_gives_equal_occupied_bin_weights():
    d=data();w=row_weights(d,'A03')
    labels=np.column_stack([d.owners,d.receiver,np.floor(d.times/5)])
    _,inv=np.unique(labels,axis=0,return_inverse=True)
    totals=np.bincount(inv,weights=w)
    np.testing.assert_allclose(totals,np.repeat(totals[0],len(totals)))


@pytest.mark.parametrize('mode',['C1','A05','A06'])
def test_frequency_density_gradient_and_alias_periodicity(mode):
    r=np.array([[0.,30.,-900.,ALIAS/2-10.,-ALIAS/2+10.]])
    logf,g,precision=density_terms(r,mode)
    # r=measurement-prediction: derivative with respect to prediction is -d/dr.
    eps=.01
    numerical=(density_terms(r-eps,mode)[0]-density_terms(r+eps,mode)[0])/(2*eps)
    np.testing.assert_allclose(g,numerical,atol=1e-9,rtol=1e-6)
    assert np.all(precision>0)
    wrapped=(r+ALIAS+ALIAS/2)%ALIAS-ALIAS/2
    np.testing.assert_allclose(logf,density_terms(wrapped,mode)[0],atol=1e-9)


@pytest.mark.parametrize('mode',['C1','A05','A06'])
def test_wrapped_density_normalization(mode):
    integral=2*sum(quad(lambda r:float(np.exp(density_terms(np.array([[r]]),mode)[0][0,0])),lo,hi,
        epsabs=1e-10)[0] for lo,hi in [(0,1000),(1000,10000),(10000,ALIAS/2)])
    assert integral==pytest.approx(1.,abs=1e-10)


def test_gaussian_one_window_specialization_matches_existing_finite_set():
    from finite_set_likelihood import prepare_finite_set_likelihood
    d=data();pred=np.column_stack([d.measured+50.,d.measured+300.])
    visible=np.array([[1,1],[1,0],[0,1],[0,0],[1,1],[1,1]],bool)
    model=SingleWindowLikelihood(d,np.zeros((6,1)),'C1')
    got=model.evaluate(pred,visible,sigma_hz=200.)
    expected=prepare_finite_set_likelihood(d.measured,d.group).evaluate(pred,visible,sigma_hz=200.,
        detection_probability=.4,clutter_rate=2.,return_gradient=True)
    assert got['total_log_likelihood']==pytest.approx(expected['total_log_likelihood'],abs=1e-12)
    np.testing.assert_allclose(got['prediction_gradient'],expected['prediction_gradient'],atol=1e-14)
    np.testing.assert_allclose(got['row_association_probability'],expected['row_association_probability'],atol=1e-14)


@pytest.mark.parametrize('mode',MODES)
def test_likelihood_gradient_including_power_weights_and_calibration(mode):
    d=data();features=np.arange(6)[:,None]/10
    model=SingleWindowLikelihood(d,features,mode)
    pred=np.column_stack([d.measured+75.,d.measured+250.])
    visible=np.ones((6,2),bool)
    result=model.evaluate(pred,visible,sigma_hz=200.)
    eps=.001;left=pred.copy();right=pred.copy();left[3,0]-=eps;right[3,0]+=eps
    num=(model.evaluate(right,visible,sigma_hz=200.)['total_log_likelihood']-
         model.evaluate(left,visible,sigma_hz=200.)['total_log_likelihood'])/(2*eps)
    assert num==pytest.approx(result['prediction_gradient'][3,0],abs=1e-8)
    np.testing.assert_allclose(result['row_association_probability'].sum(axis=1)+result['row_clutter_probability'],1.)
    assert np.all(result['irls_weights']>=0)
    if mode=='A07':
        idx=np.array([0,0,0,0,1,1]); assert np.all(result['row_association_probability'][np.arange(6),1-idx]==0)


@pytest.mark.parametrize('mode',['A08','A09','A10'])
def test_extra_prior_gradient_and_positive_semidefinite_hessian(mode):
    obj=object.__new__(Objective);obj.mode=mode
    v=np.arange(12)/10
    p,g,h=obj.extra_penalty(v)
    for i in range(len(v)):
        left,right=v.copy(),v.copy();left[i]-=1e-5;right[i]+=1e-5
        numerical=(obj.extra_penalty(right)[0]-obj.extra_penalty(left)[0])/2e-5
        assert numerical==pytest.approx(g[i],abs=1e-9)
    assert np.linalg.eigvalsh(h).min()>=-1e-12
    if mode=='A09':
        v[5]=v[3];assert obj.extra_penalty(v)[0]==pytest.approx(0.)


def test_reject_multiple_candidates_per_window():
    d=data();d.group[1]=d.group[0]
    with pytest.raises(ValueError): SingleWindowLikelihood(d,np.zeros((6,1)),'C1')
