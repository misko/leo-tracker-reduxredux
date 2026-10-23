import numpy as np
import pytest
from family_predictive import conditional, local_sensitivity


def score(y,k):
    return y@np.linalg.solve(k,y)+np.linalg.slogdet(k)[1]+len(y)*np.log(2*np.pi)


def test_conditional_matches_joint_minus_training_with_cross_covariance():
    y=np.array([3.,-2.,1.]);k=np.array([[4.,1.,.5],[1.,3.,.7],[.5,.7,2.]])
    h=np.array([True,False,True]);v=conditional(y,k,h)
    assert v['score']==pytest.approx(score(y,k)-score(y[~h],k[np.ix_(~h,~h)]))
    assert not np.allclose(v['innovation_hz'],y[h])


def test_no_training_is_marginal_and_order_permutation_invariant():
    y=np.array([2.,3.]);k=np.array([[4.,1.],[1.,5.]])
    a=conditional(y,k,[True,True]);b=conditional(y[::-1],k[::-1,::-1],[True,True])
    assert a['score']==pytest.approx(score(y,k))
    assert a['score']==pytest.approx(b['score'])


def test_invalid_or_indefinite_covariance_rejected():
    with pytest.raises(ValueError):conditional([1.],[[1.]],[False])
    with pytest.raises(np.linalg.LinAlgError):conditional([1.],[[-1.]],[True])


def test_local_information_recovers_linear_residual_sensitivity():
    class P:
        hardware=np.zeros((1,0));smooth=np.zeros((1,0));labels=[];supported=[];members=[]
        def calculate(self,x):return dict(residual=np.array([2*x[0],x[1]]),coefficient=np.array([]))
    r=local_sensitivity(P(),np.array([1.,2.]))
    assert np.allclose(r['eigenvalues'],[1.,4.])
    assert abs(r['weak_direction_east_north'][1])==pytest.approx(1.)
