"""Normalized alternatives, proper complexity and unobserved-prior collapse."""

import numpy as np
import pytest
from scipy.special import logsumexp

from ds23_unknown_polynomial import polynomial_density, phase_prior_groups, DEGREE_PRIOR, COEFFICIENT_SIGMA_HZ
from dsx01_hierarchical_bound import hierarchical_bound


def test_predictive_polynomial_matches_dense_gaussian_degree_mixture():
    times = np.linspace(10.,290.,12)
    y = 30_000.+2000.*(times-150.)/150.+np.sin(times)*70
    sigma = np.linspace(80.,140.,len(times))
    result = polynomial_density(times,y,sigma,predictive=True)
    basis = np.polynomial.polynomial.polyvander((times-150.)/150.,4)*COEFFICIENT_SIGMA_HZ
    costs=[]
    for degree in range(1,5):
        u=basis[:,:degree+1];cov=np.diag(2*sigma**2)+u@u.T
        cost=y@np.linalg.solve(cov,y)+np.linalg.slogdet(cov)[1]+len(y)*np.log(2*np.pi)
        costs.append(cost)
    np.testing.assert_allclose([r['negative_twice_elbo'] for r in result['degrees']],costs,atol=2e-5,rtol=0)
    assert result['negative_twice_elbo'] == pytest.approx(-2*logsumexp(np.log(DEGREE_PRIOR)-np.array(costs)/2),abs=2e-5)
    assert sum(result['degree_posterior']) == pytest.approx(1.)


def test_unobserved_phase_prior_has_exact_unit_integral():
    y=np.array([.2,-.1,.6]);u=np.array([[1.,0.],[2.,0.],[3.,0.]])
    collapsed=phase_prior_groups(2,0,2,[0],3.)
    a=hierarchical_bound(y,u,np.ones(3),np.zeros(3,int),prior_groups=collapsed,prior_nu=3.)
    b=hierarchical_bound(y,u[:,:1],np.ones(3),np.zeros(3,int),prior_groups=np.array([0]),prior_nu=3.)
    assert a['negative_twice_elbo'] == pytest.approx(b['negative_twice_elbo'],abs=1e-10)
    assert a['coefficient'][1] == 0.


def test_predictive_points_cannot_use_curved_fractional_power():
    with pytest.raises(ValueError,match='predictive power exactly one'):
        polynomial_density([0.,1.],[0.,1.],100.,power=.5,predictive=True)


def test_high_order_has_evidence_penalty_for_noiseless_linear_curve():
    times=np.linspace(0.,300.,40);values=20_000+100*times
    result=polynomial_density(times,values,100.)
    assert np.argmax(result['degree_posterior']) == 0
    assert result['degrees'][0]['RMS_hz'] < .01
    assert result['negative_twice_elbo'] >= min(r['negative_twice_elbo'] for r in result['degrees'])
