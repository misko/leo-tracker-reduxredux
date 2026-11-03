import numpy as np
import pytest

from ds23_channel_calibration import nonlinear_channel_basis
from dsx01_hierarchical_bound import hierarchical_bound


@pytest.mark.parametrize('observed', [[True]*4,[True,False,True,True]])
def test_channel_modes_cannot_replace_constant_or_linear_RF(observed):
    rf = np.array([10.7096875,10.9596875,11.2096875,11.4596875])
    active = np.asarray(observed)
    basis = nonlinear_channel_basis(rf,active)
    rank = active.sum()-2
    np.testing.assert_allclose(basis[active].T@np.ones(active.sum()),0,atol=1e-12)
    np.testing.assert_allclose(basis[active].T@(rf[active]-rf[active].mean()),0,atol=1e-12)
    np.testing.assert_allclose(basis[active,:rank].T@basis[active,:rank],np.eye(rank),atol=1e-12)


def test_two_channels_do_not_supply_nonlinear_calibration():
    np.testing.assert_array_equal(nonlinear_channel_basis(np.arange(4.),[True,True,False,False]),np.zeros((4,2)))


def test_unused_gaussian_calibration_modes_leave_normalized_bound_unchanged():
    rng=np.random.default_rng(67321);u=rng.normal(size=(30,3));y=rng.normal(size=30)
    original=hierarchical_bound(y,u,np.ones(30),np.repeat(np.arange(3),10))
    augmented=hierarchical_bound(y,np.column_stack((u,np.zeros((30,8)))),np.ones(30),np.repeat(np.arange(3),10))
    assert abs(original['negative_twice_elbo']-augmented['negative_twice_elbo'])<1e-10
    np.testing.assert_allclose(original['coefficient'],augmented['coefficient'][:3],atol=1e-12)
