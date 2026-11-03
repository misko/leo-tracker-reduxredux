from math import lgamma
import numpy as np
import pytest

from ds23_family_orbit_tail import joint_student_cost,family_groups,qualify
from learn_ds23_causal_phase_forecast import distribution_cost


def test_univariate_density_is_original_variance_parameterization():
    z=np.linspace(-5,5,101)
    for nu in (3.,4.,8.):
        np.testing.assert_allclose(joint_student_cost(z[:,None],nu),distribution_cost(z,np.ones(len(z)),1.,nu))


def test_joint_student_has_same_unit_covariance():
    rng=np.random.default_rng(9362);nu=5.;n=200000
    precision=rng.gamma(nu/2,2/(nu-2),n)
    samples=rng.normal(size=(n,4))/np.sqrt(precision[:,None])
    np.testing.assert_allclose(np.cov(samples.T),np.eye(4),atol=.025)
    expected=4*np.log((nu-2)*np.pi)+2*lgamma(nu/2)-2*lgamma((nu+4)/2)
    assert joint_student_cost(np.zeros((1,4)),nu)[0]==pytest.approx(expected)


def test_only_same_family_phase_and_orbit_share_precision():
    begin=11;labels=[2,5,8];supported=[2,8]
    group=family_groups(begin,labels,supported,4)
    np.testing.assert_array_equal(group[:begin],-1)
    np.testing.assert_array_equal(group[begin:begin+3],[0,1,2])
    np.testing.assert_array_equal(group[begin+3:begin+6],[0,0,0])
    np.testing.assert_array_equal(group[begin+6:begin+9],[2,2,2])
    np.testing.assert_array_equal(group[-4:],-1)


def test_qualification_requires_temporal_and_satellite_support():
    m=dict(nu=3.,shrinkage=0.,multiplier=1.)
    result=qualify([],100,m,m)
    assert not result['qualified']
    assert 'insufficient' in result['reason']
