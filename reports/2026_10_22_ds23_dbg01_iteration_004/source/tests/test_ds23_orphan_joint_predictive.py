import numpy as np
import pytest

from ds23_orphan_joint_predictive import condition_gaussian


def test_conditioning_preserves_full_shared_predictive_covariance_and_normalization():
    a=np.array([[1.,2.],[2.,0.],[.5,-1.]])
    y=np.array([2.,-1.,.5]);variance=np.array([1.,2.,3.]);groups=np.array([0,0,1])
    mean,covariance,score=condition_gaussian(a,y,variance,groups,bias_sigma=2.)
    r=np.diag(variance)+4*(groups[:,None]==groups[None,:])
    expected_covariance=np.linalg.inv(np.eye(2)+a.T@np.linalg.solve(r,a))
    np.testing.assert_allclose(covariance,expected_covariance,atol=1e-12)
    np.testing.assert_allclose(mean,expected_covariance@a.T@np.linalg.solve(r,y),atol=1e-12)
    total=r+a@a.T
    assert score==pytest.approx(y@np.linalg.solve(total,y)+np.linalg.slogdet(total)[1]+3*np.log(2*np.pi))
