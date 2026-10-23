import numpy as np
from ds23_distributed_polynomial_curvature import evidence
from ds23_supported_curvature import curvature_evidence


def test_symmetric_cubic_is_distributed_nonlinear_evidence_even_without_a_quadratic_term():
    t=np.linspace(-30,30,41);track=dict(times=t,values=t**3)
    assert not curvature_evidence(track)['qualified']
    result=evidence(track)
    assert result['qualified'] and 3 in result['degrees_selected']


def test_an_isolated_endpoint_cannot_create_distributed_curvature():
    t=np.r_[0.,np.linspace(10,40,30)];y=300*t;y[0]=40000
    assert not evidence(dict(times=t,values=y))['qualified']


def test_linear_noise_does_not_count_as250Hz_of_fitted_nonlinearity():
    t=np.linspace(0,60,60);y=200*t+np.random.default_rng(16).normal(0,400,len(t))
    assert not evidence(dict(times=t,values=y))['qualified']
