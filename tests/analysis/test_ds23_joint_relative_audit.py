import numpy as np
import pytest
from ds23_joint_relative_audit import expected_log_density,position_information
from dsx01_hierarchical_bound import hierarchical_bound


@pytest.mark.parametrize('nu',[None,4.,7.])
def test_expected_density_entropy_matches_bound_for_shared_correlated_measurements(nu):
    rng=np.random.default_rng(5342);u=rng.normal(size=(20,4));sigma=np.linspace(.7,1.4,20)
    y=u@np.array([.4,-.3,.7,.1])+rng.normal(size=20);groups=np.repeat([0,1],10)
    powers=np.array([.7,1.]);slots=[1,2];prior=np.full(4,-1);prior[slots]=np.arange(2)
    fit=hierarchical_bound(y,u,sigma,groups,powers=powers,prior_groups=None if nu is None else prior,
        prior_nu=4 if nu is None else nu,iterations=1000)
    check=expected_log_density(y,u,sigma,groups,powers,np.zeros(4),np.ones(4),fit['coefficient'],
        fit['noise_precision'],fit['coefficient_prior_precision'],slots,nu)
    assert abs(check['negative_twice_elbo']-fit['negative_twice_elbo'])<1e-4
    assert check['maximum_coefficient_normal_equation_error']<1e-10


def test_nuisance_projection_matches_analytic_common_bias_variance():
    # Independent east/north observations each have variance1; an uncertain
    # east-only offset has variance9. Marginal position variances are10,1.
    r=position_information(np.eye(2),np.array([[1.],[0.]]),np.ones(2),np.array([1/9]))
    np.testing.assert_allclose(r['local_position_covariance_km2'],np.diag([10.,1.]),atol=1e-12)
    assert r['fraction_trace_information_retained']==pytest.approx(.55)


def test_independent_opposing_evidence_cancels_bias_information_loss():
    j=np.array([[1.,0.],[1.,0.],[0.,1.]])
    u=np.array([[1.],[-1.],[0.]])
    r=position_information(j,u,np.ones(3),np.array([.01]))
    np.testing.assert_allclose(r['local_position_covariance_km2'],np.diag([.5,1.]),atol=1e-12)
    assert r['fraction_trace_information_retained']==pytest.approx(1.)
