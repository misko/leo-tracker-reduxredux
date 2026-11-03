import numpy as np
import pytest
from ds23_exact_differential_phase import refine_pair
from probe_ds23_differential_catalogue import pair_screen


def test_exact_linear_model_reproduces_integrated_tangent_score():
    t=np.linspace(-1,1,35);f=np.array([100+30*t+8*t*t,-200+50*t-5*t*t])
    d=np.array([30+16*t,50-10*t]);sd=np.array([.4,.7]);mu=np.array([.1,-.2])
    y=f[1]-f[0]+d[1]*.3-d[0]*.2+15+np.sin(5*t)
    old=pair_screen(y,f,d,sd,2.);k=np.flatnonzero((old['first']==0)&(old['second']==1))[0]
    def predict(phase):return f[1]-f[0]+d[1]*(phase[1]-mu[1])-d[0]*(phase[0]-mu[0])
    result=refine_pair(y,predict,mu,sd,2.,mu)
    assert result['valid_local_nomination']
    assert abs(result['local_Laplace_score']-old['cost'][k])<1e-5
    np.testing.assert_allclose(result['phase_s'],mu+sd*old['coefficient'][k,:2],atol=1e-5)


def test_exact_nonlinear_phase_recovers_curved_relative_signal():
    t=np.linspace(-10,10,41)
    def predict(phase):return .03*(t+phase[1])**4-2*(t+phase[0])**2
    truth=np.array([2.,-1.]);y=predict(truth)+17
    result=refine_pair(y,predict,[0.,0.],[3.,3.],.1,[1.5,-.5])
    assert result['valid_local_nomination'] and result['RMS_hz']<.02
    np.testing.assert_allclose(result['phase_s'],truth,atol=.01)


def test_bad_frequency_uncertainty_rejected():
    with pytest.raises(ValueError):refine_pair(np.arange(5.),lambda x:np.arange(5.),[0,0],[1,1],0,[0,0])
