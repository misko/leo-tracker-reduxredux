from pathlib import Path
import sys
import numpy as np
import pytest
from scipy.special import digamma, gammaln, logsumexp
from scipy.stats import t, entropy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'tools'))
from ds23_sparse_glitch_noise import glitch_bound, predictive_glitch_bound
from ds23_observation_noise import observation_bound
from ds23_frozen_precision import conditional_gaussian


def test_equal_component_variances_reproduce_original_fragment_Gamma_model():
    rng = np.random.default_rng(2929); y = rng.normal(size=32); u = rng.normal(size=(32, 6))
    owners = np.repeat([0, 1], 16); powers = [.7, 1.]; prior = np.array([-1, 0, 0, -1, -1, -1])
    old = observation_bound(y, u, 1.2, owners, owners, powers=powers, prior_groups=prior)
    new = glitch_bound(y, u, 1.2, owners, powers=powers, prior_groups=prior, glitch_sd_ratio=1.)
    for key in ['coefficient', 'noise_precision', 'coefficient_prior_precision', 'negative_twice_elbo']:
        np.testing.assert_allclose(new[key], old[key], atol=1e-10, rtol=1e-10)
    np.testing.assert_allclose(new['glitch_probability'], .01, atol=1e-15)


@pytest.mark.parametrize('value', [0., 2., 10.])
def test_reported_cost_matches_direct_ELBO_and_bounds_exact_single_point_mixture(value):
    epsilon, ratio = .01, 10.
    result = glitch_bound(np.array([value]), np.zeros((1, 0)), 1., np.array([0]),
                          glitch_probability=epsilon, glitch_sd_ratio=ratio)
    rho = result['glitch_probability'][0]
    variances = np.array([1., ratio**2])/(1-epsilon+epsilon*ratio**2)
    alpha0 = beta0 = 2.; alpha = 2.5; rate = alpha/result['noise_precision'][0]
    elogtau = digamma(alpha)-np.log(rate)
    qz = np.array([1-rho, rho]); prior_z = np.array([1-epsilon, epsilon])
    expected_loglike = -.5*(np.log(2*np.pi)+qz@np.log(variances)-elogtau+
                                  alpha/rate*value**2*(qz@(1/variances)))
    gamma_KL = (alpha-alpha0)*digamma(alpha)-gammaln(alpha)+gammaln(alpha0)+alpha0*np.log(rate/beta0)+alpha*(beta0/rate-1)
    cat_KL = np.sum(np.where(qz>0, qz*np.log(np.maximum(qz, 1e-300)/prior_z), 0.))
    direct = -2*(expected_loglike-gamma_KL-cat_KL)
    assert result['negative_twice_elbo'] == pytest.approx(direct, abs=2e-8)
    exact = -2*logsumexp(np.log(prior_z)+t.logpdf(value, df=4, scale=np.sqrt(variances)))
    assert result['negative_twice_elbo'] >= exact-1e-9


def test_sparse_glitch_keeps_fragment_precision_without_dropping_the_outlier():
    y = np.r_[np.tile([-.1, 0., .1], 10), 15.]; owners = np.zeros(len(y), int); u = np.ones((len(y), 1))
    ordinary = observation_bound(y, u, 1., owners, owners)
    robust = glitch_bound(y, u, 1., owners)
    assert robust['glitch_probability'][-1] > .8
    assert np.max(robust['glitch_probability'][:-1]) < .05
    assert robust['noise_precision'][0] > ordinary['noise_precision'][0]*5
    assert robust['point_relative_precision'][-1] > 0
    assert len(robust['conditional_residual_hz']) == len(y)
    assert robust['negative_twice_elbo'] < ordinary['negative_twice_elbo']


def test_full_covariance_and_fractional_power_cost_match_direct_mean_field_ELBO():
    rng = np.random.default_rng(7171); owners = np.repeat([0, 1, 2], [10, 12, 8])
    u = rng.normal(size=(len(owners), 4)); y = rng.normal(size=len(owners)); y[-1] += 12
    sigma = rng.uniform(.7, 1.3, len(y)); power = np.array([.4, .7, 1.])
    result = glitch_bound(y, u, sigma, owners, powers=power)
    rho = result['glitch_probability']; relative = result['point_relative_precision']; tau = result['noise_precision']
    w = power[owners]*tau[owners]*relative/sigma**2
    gram = np.eye(4)+u.T@(u*w[:, None]); cov = np.linalg.inv(gram); mean = result['coefficient']
    energy = (y-u@mean)**2+np.sum((u@cov)*u, axis=1)
    alpha0 = beta0 = 2.; alpha = alpha0+power*np.bincount(owners)/2; rate = alpha/tau
    elogtau = digamma(alpha)-np.log(rate); variances = np.array([1., 100.])/1.99
    logvariance = (1-rho)*np.log(variances[0])+rho*np.log(variances[1])
    loglike = -.5*np.sum(power[owners]*(np.log(2*np.pi)+2*np.log(sigma)+logvariance-elogtau[owners]+
                                              tau[owners]*relative*energy/sigma**2))
    theta_KL = .5*(np.trace(cov)+mean@mean-4-np.linalg.slogdet(cov)[1])
    gamma_KL = np.sum((alpha-alpha0)*digamma(alpha)-gammaln(alpha)+gammaln(alpha0)+alpha0*np.log(rate/beta0)+alpha*(beta0/rate-1))
    cat_KL = float(entropy(np.column_stack((rho, 1-rho)), [.01, .99], axis=1).sum())
    direct = -2*(loglike-theta_KL-gamma_KL-cat_KL)
    assert result['negative_twice_elbo'] == pytest.approx(direct, abs=2e-8)


def test_predictive_mixture_retains_full_covariance_and_exact_Gaussian_control():
    rng = np.random.default_rng(4646); n, d = 28, 5
    u = rng.normal(size=(n, d)); y = rng.normal(size=n); sigma = rng.uniform(.7, 1.3, n)
    old = conditional_gaussian(y, u, sigma, np.ones(n), np.ones(n), np.ones(d), 1.)
    for epsilon, ratio in [(0., 10.), (.01, 1.)]:
        new = predictive_glitch_bound(y, u, sigma, epsilon, ratio)
        assert new['objective'] == pytest.approx(old['objective'], abs=1e-9)
        np.testing.assert_allclose(new['coefficient'], old['coefficient'], atol=1e-10)


def test_predictive_cost_matches_independent_Gaussian_categorical_ELBO():
    rng = np.random.default_rng(5454); n, d = 25, 3
    u = rng.normal(size=(n, d)); y = rng.normal(size=n); y[-1] = 15; sigma = np.ones(n)
    fit = predictive_glitch_bound(y, u, sigma)
    rho = fit['glitch_probability']; variances = np.array([1., 100.])/1.99
    relative = (1-rho)/variances[0]+rho/variances[1]
    cov = np.linalg.inv(np.eye(d)+u.T@(u*relative[:, None])); mean = fit['coefficient']
    energy = (y-u@mean)**2+np.sum((u@cov)*u, axis=1)
    expected_loglike = -.5*np.sum(np.log(2*np.pi)+(1-rho)*np.log(variances[0])+rho*np.log(variances[1])+relative*energy)
    kl_gaussian = .5*(np.trace(cov)+mean@mean-d-np.linalg.slogdet(cov)[1])
    kl_categorical = float(entropy(np.column_stack((rho, 1-rho)), [.01, .99], axis=1).sum())
    assert fit['objective'] == pytest.approx(-2*(expected_loglike-kl_gaussian-kl_categorical), abs=1e-9)
    assert rho[-1] > .9
