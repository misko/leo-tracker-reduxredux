import numpy as np
import pytest
from audit_ds23_differential_phase_tangents import profile_constant


def test_profiled_relative_constant_matches_dense_gaussian_density():
    y=np.array([[1.,4.,-2.],[6.,2.,3.]]);sigma=2.;prior=3.
    result=profile_constant(y,sigma,prior)
    covariance=sigma**2*np.eye(3)+prior**2*np.ones((3,3))
    expected=np.einsum('ni,ij,nj->n',y,np.linalg.inv(covariance),y)+np.linalg.slogdet(covariance)[1]-3*np.log(sigma**2)
    np.testing.assert_allclose(result['cost'],expected,atol=1e-12)
    np.testing.assert_allclose(result['bias_hz'],y.sum(axis=1)/(3+sigma**2/prior**2))


def test_invalid_noise_or_nonbatched_data_rejected():
    with pytest.raises(ValueError):profile_constant([1.,2.],1.)
    with pytest.raises(ValueError):profile_constant([[1.,2.]],0.)
