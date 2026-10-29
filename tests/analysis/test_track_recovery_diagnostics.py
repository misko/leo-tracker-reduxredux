import numpy as np
import pytest
from leo.analysis.research.track_recovery_diagnostics import profile_rate,shortlist
from leo.analysis.research.retained_track_likelihood import PERIOD


def test_alias_rate_is_regularized_and_not_free_polynomial():
    t=np.linspace(0,100,101);f=3*t*t;y=f+PERIOD+40+.4*(t-t.mean())
    base=profile_rate(y,f,t);fit=profile_rate(y,f,t,rate_sigma_hz_s=.5)
    assert fit['alias'][0]==-1
    assert 0<fit['rate_hz_s'][0]<.4
    assert fit['rms_hz'][0]<base['rms_hz'][0]
    assert abs(fit['bias_hz'][0]-40)<.1
    with pytest.raises(ValueError):profile_rate(y,f,t,rate_sigma_hz_s=-1)


def test_shortlist_keeps_distinct_runner_up_and_visibility():
    grid=np.arange(31.);phases=np.array([-1.,0.,1.]);freq=np.empty((3,3,len(grid)))
    for k,phase in enumerate(phases):
        for j in range(3):freq[k,j]=(grid+phase)**2*(1+j*.1)
    elev=np.full_like(freq,20.);elev[:,2]=-1
    rows=shortlist(grid**2,grid,1.,freq,elev,grid,phases,top=3)
    assert [r['candidate_index'] for r in rows]==[0,1]
    assert rows[0]['phase_s']==0


def test_profile_matches_dense_marginal_gaussian_cost():
    # A scientific reference calculation verifies the prior and determinant
    # penalty, independently of the centered closed-form implementation.
    t=np.array([0.,1.,5.,11.,25.]);x=t-t.mean();y=np.array([20.,31.,-9.,4.,44.])
    noise,bias,rate=13.,55.,.7
    result=profile_rate(y,np.zeros(len(t)),t,noise_hz=noise,bias_sigma_hz=bias,rate_sigma_hz_s=rate)
    design=np.column_stack((np.ones(len(t))*bias,x*rate))
    covariance=noise**2*np.eye(len(t))+design@design.T
    expected=y@np.linalg.solve(covariance,y)+np.linalg.slogdet(covariance)[1]-len(t)*np.log(noise**2)
    assert result['cost'][0]==pytest.approx(expected,rel=1e-12)
