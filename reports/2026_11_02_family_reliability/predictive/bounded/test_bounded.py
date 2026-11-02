import numpy as np
from scipy.integrate import dblquad
from scipy.stats import multivariate_normal
from bounded import box_log_probability,scipy_box_probability,correct_score,condition_position


def test_deterministic_box_quadrature_matches_scipy_and_direct_integration():
    mean=np.array([.7,-.4]);cov=np.array([[2.,.8],[.8,1.3]]);low=(-1.2,-.9);high=(1.6,1.1)
    value=np.exp(box_log_probability(mean,cov,low,high)['log_probability'])
    dense=dblquad(lambda y,x:multivariate_normal.pdf([x,y],mean=mean,cov=cov),low[0],high[0],lambda x:low[1],lambda x:high[1],epsabs=1e-10)[0]
    assert abs(value-dense)<1e-10
    assert abs(value-scipy_box_probability(mean,cov,low,high))<1e-8


def test_broad_box_recovers_original_normalized_density():
    rng=np.random.default_rng(21);n=12;r=rng.normal(size=n);s=rng.uniform(.5,2,n);u=rng.normal(size=(n,3));j=rng.normal(size=(n,2));mean=np.array([1.,-2.]);cov=np.array([[2.,.4],[.4,1.]])
    result=correct_score(100.,r,s,u,j,mean,cov,(-1000.,-1000.),(1000.,1000.))
    assert abs(result['negative_twice_log_density']-100.)<1e-10


def test_position_conditioning_matches_full_dense_joint_gaussian():
    rng=np.random.default_rng(22);n=9;r=rng.normal(size=n);s=rng.uniform(.5,2,n);u=rng.normal(size=(n,3));j=rng.normal(size=(n,2));mean=np.array([1.,-2.]);cov=np.array([[2.,.4],[.4,1.]])
    m2,s2=condition_position(r,s,u,j,mean,cov)
    full=np.diag(s*s)+u@u.T+j@cov@j.T
    assert np.allclose(m2,mean+cov@j.T@np.linalg.solve(full,r))
    assert np.allclose(s2,cov-cov@j.T@np.linalg.solve(full,j@cov))
