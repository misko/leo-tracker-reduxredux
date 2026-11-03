from pathlib import Path
import sys
import numpy as np
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from ds23_cross_RX_gain_prediction import fit,predict,loss


def common_gain():
    rng=np.random.default_rng(17);t=np.arange(40)/750
    phase=rng.uniform(-np.pi,np.pi,len(t));s=np.exp(1j*phase);variance=.01
    a=s+np.sqrt(variance/2)*(rng.normal(size=len(t))+1j*rng.normal(size=len(t)))
    b=.8*np.exp(.6j+2j*np.pi*34*t)*s+np.sqrt(variance/2)*(rng.normal(size=len(t))+1j*rng.normal(size=len(t)))
    return t,a,b,np.full(len(t),variance),np.full(len(t),variance)


def test_shared_random_phase_predicts_held_target_without_transmitter_continuity():
    t,a,b,va,vb=common_gain();train=np.arange(len(t))%2==0;test=~train
    shared=fit(t[train],a[train],b[train],va[train],vb[train]);independent=fit(t[train],a[train],b[train],va[train],vb[train],shared=False)
    # Half-rate training frames admit frequency aliases; held frames resolve them.
    assert predict(shared,t[test],a[test],b[test],va[test],vb[test])<predict(independent,t[test],a[test],b[test],va[test],vb[test])-20
    assert abs(shared['frequency_correction_mod750_hz']-34)<3


def test_source_noise_is_in_the_conditional_density():
    t=np.arange(5.)/750;a=np.ones(5,complex);b=np.full(5,3+0j);p=[1,0,0,-16]
    small=loss(p,t,a,b,np.full(5,.01),np.full(5,.01),shared=True,prior=False)
    large=loss(p,t,a,b,np.full(5,1.),np.full(5,.01),shared=True,prior=False)
    assert large<small


def test_density_scale_restored_when_training_gains_are_rescaled():
    t,a,b,va,vb=common_gain();m=fit(t[:24],a[:24],b[:24],va[:24],vb[:24]);k=3.
    n=fit(t[:24],a[:24]*k,b[:24]*k,va[:24]*k*k,vb[:24]*k*k)
    first=predict(m,t[24:],a[24:],b[24:],va[24:],vb[24:])
    second=predict(n,t[24:],a[24:]*k,b[24:]*k,va[24:]*k*k,vb[24:]*k*k)
    assert abs(second-first-2*len(t[24:])*np.log(k))<1e-3


def test_invalid_gain_variances_are_explicit():
    t,a,b,va,vb=common_gain()
    with pytest.raises(ValueError):fit(t,a,b,np.zeros(len(t)),vb)


def test_channel_shape_is_not_trained_on_target_held_frames():
    from probe_ds23_cross_RX_gain_prediction import projected_gains
    rng=np.random.default_rng(4);c=rng.normal(size=(12,8))+1j*rng.normal(size=(12,8))
    covariance=np.broadcast_to(np.eye(8),(12,8,8)).copy();train=np.arange(12)%2==0
    a=projected_gains(c,covariance,train);changed=c.copy();changed[~train]*=100.
    b=projected_gains(changed,covariance,train)
    np.testing.assert_allclose(a['gain'][train],b['gain'][train],atol=1e-12,rtol=0)
    np.testing.assert_allclose(a['variance'],b['variance'],atol=1e-12,rtol=0)
