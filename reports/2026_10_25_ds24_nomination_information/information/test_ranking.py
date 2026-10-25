"""Small independent local-Gaussian covariance/ownership controls."""

import numpy as np
from ranking import gain, solve
from ds23_position_information import marginal_position_information


def test_conditional_gain_equals_one_joint_nuisance_elimination():
    rng = np.random.default_rng(2026102517)
    j, u = rng.normal(size=(37,2)), rng.normal(size=(37,6))
    w, prior = np.exp(rng.normal(size=37)), np.exp(rng.normal(size=6))
    jt, ht, extra = rng.normal(size=(11,2)), rng.normal(size=(11,6)), rng.normal(size=(11,4))
    variance = np.exp(rng.normal(size=11))
    root = np.linalg.cholesky(np.diag(prior)+u.T@(w[:,None]*u))
    info = marginal_position_information(j,u,w,prior)
    delta, covariance, effective = gain(jt,ht,variance,extra,root,solve(root,u.T@(w[:,None]*j)))
    full_u = np.vstack((np.column_stack((u,np.zeros((len(u),4)))),np.column_stack((ht,extra))))
    full = marginal_position_information(np.vstack((j,jt)),full_u,np.r_[w,1/variance],np.r_[prior,np.ones(4)])
    np.testing.assert_allclose(info+delta,full,rtol=1e-11,atol=1e-11)
    np.testing.assert_allclose(delta,effective.T@np.linalg.solve(covariance,effective),rtol=1e-11,atol=1e-11)


def test_same_family_copies_share_uncertainty_and_do_not_double_information():
    # An uncertain shared family offset persists as repeated owner noise drops.
    j=np.array([[1.,0.],[1.,0.]])
    h=np.zeros((2,1));root=np.eye(1);response=np.zeros((1,2))
    shared=np.ones((2,1))*10.
    copied=np.eye(2)*10.
    a,_,_=gain(j,h,np.ones(2),shared,root,response)
    b,_,_=gain(j,h,np.ones(2),copied,root,response)
    assert a[0,0] < b[0,0]
    np.testing.assert_allclose(a[0,0],2/201.,rtol=1e-12)


def test_old_predictive_conditioning_keeps_shared_radio_covariance():
    # An old predictive source constrains the same radio coordinate as target.
    j=np.eye(2);h=np.ones((2,1));variance=np.ones(2)
    extra=np.empty((2,0));response=np.zeros((1,2))
    prior,_,_=gain(j,h,variance,extra,np.eye(1),response)
    conditioned,_,_=gain(j,h,variance,extra,np.array([[3.]]),response)
    assert np.linalg.eigvalsh(conditioned-prior).min() > -1e-12
    assert np.trace(conditioned)>np.trace(prior)
