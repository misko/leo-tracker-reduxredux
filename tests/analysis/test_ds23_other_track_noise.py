import numpy as np
import pytest

from ds23_other_track_noise import blocks,shape_score,fit_shape,validation


def test_weighted_polynomial_contrasts_remove_a_native_curve_with_heterogeneous_sigma():
    t=np.linspace(0,30,20);track=dict(key='a',times=t,values=1000+30*t+t*t,observation_ids=[str(i) for i in range(len(t))],pieces=[dict(start_s=0,end_s=30,degree=2)])
    sigma={str(i):1+i for i in range(len(t))}
    assert blocks([track],sigma,1.)==[]


def test_reml_correlated_score_matches_direct_dense_covariance():
    rng=np.random.default_rng(4);t=np.linspace(0,20,17);design=np.column_stack((np.ones(len(t)),t))
    q,_=np.linalg.qr(design,mode='complete');b=q[:,2:];z=rng.normal(size=b.shape[1]);p=dict(times=t,basis=b,contrast=z)
    score,scale=shape_score(p,.6,3.)
    r=.4*np.eye(len(t))+.6*np.exp(-abs(t[:,None]-t)/3);k=b.T@r@b
    expected=len(z)*np.log(z@np.linalg.solve(k,z)/len(z))+np.linalg.slogdet(k)[1]
    assert score==pytest.approx(expected,abs=1e-10) and scale>0


def test_insufficient_other_track_evidence_cannot_qualify_a_covariance():
    assert not fit_shape([])['qualified']
    assert not validation([],dict(alpha=.6,tau_s=3))['positive_target_gain']
