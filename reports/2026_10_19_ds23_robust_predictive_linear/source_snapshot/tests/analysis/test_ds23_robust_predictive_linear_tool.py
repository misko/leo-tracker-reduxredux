from math import lgamma
from types import SimpleNamespace
import numpy as np
import pytest
from ds23_robust_predictive_linear import predictive_bound,attach_robust_linear


def test_no_design_matches_exact_grouped_student_noise_density():
    y=np.array([.2,-.3,.7,2.]);sigma=np.array([1.,2.,1.3,.8]);nu=4.
    r=predictive_bound(y,np.empty((4,0)),np.empty((0,0)),sigma,np.zeros(4,int),bias_sigma=0.)
    n=len(y);energy=np.sum((y/sigma)**2)
    expected=-2*lgamma((nu+n)/2)+2*lgamma(nu/2)+n*np.log(nu*np.pi)+2*np.log(sigma).sum()+(nu+n)*np.log1p(energy/nu)
    assert r['negative_twice_elbo']==pytest.approx(expected,abs=1e-9)


def test_inconsistent_new_group_downweights_itself_without_downweighting_other_group():
    rng=np.random.default_rng(91);y=rng.normal(size=60);y[30:]*=30
    r=predictive_bound(y,np.empty((60,0)),np.empty((0,0)),np.ones(60),np.repeat([0,1],30),bias_sigma=0.)
    assert r['noise_precision'][1]<r['noise_precision'][0]/100


def test_student_bias_keeps_gaussian_variance_scale_but_tolerates_large_constants():
    y=np.full(40,20.);u=np.empty((40,0));a=np.empty((0,0));s=np.ones(40);g=np.zeros(40,int)
    gaussian=predictive_bound(y,u,a,s,g,bias_sigma=1.)
    student=predictive_bound(y,u,a,s,g,bias_sigma=1.,student_bias=True)
    assert student['negative_twice_elbo']<gaussian['negative_twice_elbo']
    assert student['predictive_bias_prior_precision'][0]<.1
    assert abs(student['predictive_bias_coefficient'][0]-20)<.1


def test_new_measurements_never_update_curved_coefficients_or_precisions(monkeypatch):
    import ds23_robust_predictive_linear as module
    p=SimpleNamespace(noise_groups=np.array([0,0]),keep=np.ones(2,bool),point_noise=np.ones(2))
    def curved(_):
        return dict(features=np.ones((2,1)),noise_precision=np.ones(1),coefficient_prior_precision=np.ones(1),
            coefficient=np.array([2.]),negative_twice_elbo=7.,normalization_constant=3.,residual=np.array([1.,2.]))
    p.calculate=curved
    view=SimpleNamespace(q=np.ones(8))
    monkeypatch.setattr(module,'linear_geometry',lambda *a:(view,np.full(8,1000.),np.ones(8),np.zeros(8,int),[slice(0,8)]))
    monkeypatch.setattr(module,'geometry_features',lambda *a:dict(intercept=np.zeros(8),features=np.ones((8,1)),elevation=np.ones(8)))
    attach_robust_linear(p,[dict()],np.ones(1),student_bias=True)
    c=p.calculate(np.zeros(2));np.testing.assert_array_equal(c['coefficient'],[2.])
    np.testing.assert_array_equal(c['noise_precision'],[1.]);np.testing.assert_array_equal(c['coefficient_prior_precision'],[1.])
    np.testing.assert_array_equal(c['linear_raw_prediction_residual_hz'],np.full(8,998.))


def test_invalid_bias_and_empty_extension():
    p=object();assert attach_robust_linear(p,[],None) is p
    with pytest.raises(ValueError):predictive_bound(np.ones(2),np.ones((2,1)),np.eye(1),np.ones(2),np.zeros(2,int),bias_sigma=-1.)
