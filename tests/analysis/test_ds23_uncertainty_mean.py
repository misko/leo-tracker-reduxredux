import numpy as np
import pytest

from ds23_uncertainty_mean import gaussian_nodes,projected_mean_shift


@pytest.mark.parametrize('rule',['spherical','hermite3'])
def test_positive_nodes_preserve_correlated_moments_and_quadratic_expectation(rule):
    mean=np.array([.2,-.4,1.]);a=np.array([[.3,0,0],[.1,.5,0],[-.2,.1,.7]]);cov=a@a.T
    x,w=gaussian_nodes(mean,cov,rule)
    assert np.all(w>0) and abs(w.sum()-1)<1e-14
    np.testing.assert_allclose(w@x,mean,atol=1e-14)
    np.testing.assert_allclose((x-mean).T@((x-mean)*w[:,None]),cov,atol=1e-14)
    h=np.array([[1.,.1,.4],[.1,2.,-.3],[.4,-.3,.5]])
    expected=mean@h@mean+np.trace(h@cov)
    assert abs(w@np.einsum('ni,ij,nj->n',x,h,x)-expected)<1e-14


def test_projected_shift_matches_augmented_joint_least_squares_and_sign():
    rng=np.random.default_rng(87);u=rng.normal(size=(20,4));j=rng.normal(size=(20,2));w=np.exp(rng.normal(size=20));v=np.array([.5,1.,2.,3.])
    truth=np.array([.3,-.2]);bias=-j@truth
    result=projected_mean_shift(j,u,w,v,bias)
    np.testing.assert_allclose(result['predicted_position_shift_km'],truth,atol=1e-14)
    bias=rng.normal(size=20)
    full=np.block([[j*np.sqrt(w)[:,None],u*np.sqrt(w)[:,None]],[np.zeros((4,2)),np.diag(np.sqrt(v))]])
    expected=np.linalg.lstsq(full,np.r_[-bias*np.sqrt(w),np.zeros(4)],rcond=None)[0][:2]
    np.testing.assert_allclose(projected_mean_shift(j,u,w,v,bias)['predicted_position_shift_km'],expected,atol=1e-14)
