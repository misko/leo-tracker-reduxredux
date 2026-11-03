import math

import numpy as np
import pytest
from scipy.integrate import quad

from ds23_hierarchical_predictive import predictive_bound


def test_zero_calibration_uncertainty_matches_exact_multivariate_student_density():
    raw, sigma = np.array([.2,-1.,2.]), np.array([.7,1.3,2.])
    result = predictive_bound(raw, np.empty((3,0)), np.empty((0,0)), sigma,
                              np.zeros(3,int), bias_sigma_hz=0.)
    n, nu = len(raw), 4.
    logp = (math.lgamma((nu+n)/2)-math.lgamma(nu/2)-n/2*np.log(nu*np.pi)-np.log(sigma).sum()
            -(nu+n)/2*np.log1p(np.sum((raw/sigma)**2)/nu))
    assert result['negative_twice_elbo'] == pytest.approx(-2*logp, abs=1e-10)


def test_shared_calibration_variational_bound_is_below_exact_predictive_evidence():
    raw, sigma = np.array([.5,-1.]), np.array([.7,1.3])
    design, precision = np.array([[1.],[2.]]), np.array([[4.]])
    result = predictive_bound(raw, design, precision, sigma, np.zeros(2,int), bias_sigma_hz=.4)
    def density(tau):
        covariance = design@np.linalg.inv(precision)@design.T + .4**2 + np.diag(sigma**2/tau)
        loglike = -.5*(raw@np.linalg.solve(covariance,raw)+np.linalg.slogdet(covariance)[1]+2*np.log(2*np.pi))
        logprior = 2*np.log(2.)-math.lgamma(2.)+np.log(tau)-2*tau
        return np.exp(loglike+logprior)
    exact, error = quad(density,0,np.inf,epsabs=1e-11,epsrel=1e-10)
    assert error < 1e-9
    assert result['negative_twice_elbo'] >= -2*np.log(exact)-1e-9
    assert result['negative_twice_elbo'] - (-2*np.log(exact)) < 1.


def test_anomalous_predictive_group_changes_its_noise_not_other_groups_data():
    raw=np.array([.1,-.1,.2,-.2,100.,-100.,100.,-100.])
    saved=raw.copy()
    result=predictive_bound(raw,np.empty((8,0)),np.empty((0,0)),np.ones(8),
                            np.repeat([0,1],4),bias_sigma_hz=0.)
    assert result['noise_precision'][1] < result['noise_precision'][0]*.001
    np.testing.assert_array_equal(raw,saved)


def test_noise_only_predictor_reproduces_the_preexisting_student_predictive_model():
    from ds23_robust_predictive_linear import predictive_bound as existing
    rng=np.random.default_rng(79)
    y=rng.normal(size=12)
    design=rng.normal(size=(12,3))
    precision=np.diag([2.,3.,4.])
    groups=np.repeat([4,9],6)
    sigma=np.linspace(.5,1.5,12)
    old=existing(y,design,precision,sigma,groups,student_bias=False,bias_sigma=.7)
    new=predictive_bound(y,design,precision,sigma,groups,bias_sigma_hz=.7)
    assert new['negative_twice_elbo']==pytest.approx(old['negative_twice_elbo'],abs=1e-10)
    np.testing.assert_allclose(new['noise_precision'],old['noise_precision'],atol=1e-12)
