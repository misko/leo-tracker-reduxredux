"""Numerical oracles for fixed Gaussian integration and its profile control."""

import numpy as np
import pytest

from ds23_frozen_precision import arm_prior_precision,conditional_gaussian


def example(power=1.):
    rng=np.random.default_rng(21)
    y=rng.normal(size=7);u=rng.normal(size=(7,4));s=np.linspace(.7,1.4,7)
    tau=np.linspace(.4,1.3,7);p=np.array([.6,1.1,2.,3.])
    return y,u,s,np.full(7,power),tau,p


def test_marginal_matches_dense_data_covariance():
    y,u,s,power,tau,prior=example()
    r=conditional_gaussian(y,u,s,power,tau,prior,1.)
    cov=np.diag(s*s/tau)+(u/prior)@u.T
    expected=y@np.linalg.solve(cov,y)+np.linalg.slogdet(cov)[1]+len(y)*np.log(2*np.pi)
    np.testing.assert_allclose(r['objective'],expected,rtol=1e-12)
    np.testing.assert_allclose(r['coefficient'],(u.T@np.linalg.solve(cov,y))/prior,rtol=1e-12)


def test_fractional_powers_and_profile_augmented_least_squares():
    y,u,s,power,tau,prior=example(.4)
    root=np.sqrt(power*tau)/s
    a=np.vstack((u*root[:,None],np.diag(np.sqrt(prior))))
    b=np.r_[y*root,np.zeros(len(prior))]
    expected=np.linalg.lstsq(a,b,rcond=None)[0]
    m=conditional_gaussian(y,u,s,power,tau,prior,1.)
    p=conditional_gaussian(y,u,s,power,tau,prior,0.)
    np.testing.assert_allclose(p['coefficient'],expected,rtol=1e-12)
    np.testing.assert_allclose(p['quadratic'],np.sum((b-a@expected)**2),rtol=1e-12)
    assert m['objective']-p['objective']==pytest.approx(m['logvolume'])
    np.testing.assert_array_equal(m['coefficient'],p['coefficient'])
    assert p['residual']@p['residual']==pytest.approx(p['quadratic'])
    assert p['normalization_constant']==pytest.approx(np.sum(power*np.log(2*np.pi*s*s/tau)))


def test_fitted_c_inserts_unit_prior_at_ninth_hardware_column():
    p=np.arange(1,16,dtype=float)
    q=arm_prior_precision(p,True)
    np.testing.assert_array_equal(q[:8],p[:8])
    assert q[8]==1.
    np.testing.assert_array_equal(q[9:],p[8:])
    np.testing.assert_array_equal(arm_prior_precision(p,False),p)


def test_zero_design_integrates_to_one_and_invalid_scales_rejected():
    y,u,s,power,tau,prior=example()
    r=conditional_gaussian(y,u*0,s,power,tau,prior,1.)
    assert r['logvolume']==pytest.approx(0,abs=1e-12)
    assert r['objective']==pytest.approx(np.sum(y*y*tau/(s*s))+r['normalization_constant'])
    with pytest.raises(ValueError):conditional_gaussian(y,u,s,power,tau*0,prior,0.)
    with pytest.raises(ValueError):arm_prior_precision(np.zeros(8),True)
