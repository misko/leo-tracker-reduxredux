import numpy as np
import pytest
from phase_factor import phase_evidence,predictive_evidence,update_candidates,update_pair_candidates

def test_one_free_phase_has_no_direction_information():
    np.testing.assert_allclose(phase_evidence([1.2],[[0],[1],[2]],[3.]),0,atol=1e-14)

def test_shared_phase_invariance_preserves_shape():
    t=np.linspace(0,1,12);y=.7+2*t**2;p=np.stack([2*t**2,-3*t])
    a=phase_evidence(y,p,np.full(12,2.))
    b=phase_evidence(y+1.1,p,np.full(12,2.))
    np.testing.assert_allclose(a,b)
    assert a[0]>a[1]

def test_zero_quality_neutral_and_unqualified_no_update():
    e=phase_evidence([.2,.5],[[0,1],[2,1]],[0,0])
    np.testing.assert_allclose(e,0)
    np.testing.assert_allclose(update_candidates(np.log([.3,.7]),[100,-100],False),[.3,.7])

def test_predictive_factor_is_joint_minus_train():
    y=np.array([.1,.2,.3,.4]);p=np.array([[0,.1,.2,.3],[0,.4,1,2]]);k=np.ones(4);mask=np.array([True,False,True,False])
    np.testing.assert_allclose(predictive_evidence(y,p,k,mask),phase_evidence(y,p,k)-phase_evidence(y[mask],p[:,mask],k[mask]))

def test_invalid_values_rejected():
    with pytest.raises(ValueError):phase_evidence([1],[0],[-1])

def test_pair_factor_updates_joint_once_and_preserves_uncertainty():
    r=update_pair_candidates(np.log([.6,.4]),np.log([.7,.3]),[[0,2],[2,0]])
    expected=np.array([[.6*.7,.6*.3*np.exp(2)],[.4*.7*np.exp(2),.4*.3]])
    expected/=expected.sum()
    np.testing.assert_allclose(r['joint'],expected)
    np.testing.assert_allclose(r['left'],expected.sum(axis=1))
    np.testing.assert_allclose(r['right'],expected.sum(axis=0))
    neutral=update_pair_candidates(np.log([.6,.4]),np.log([.7,.3]),[[0,100],[100,0]],False)
    np.testing.assert_allclose(neutral['left'],[.6,.4])
    np.testing.assert_allclose(neutral['right'],[.7,.3])
