import numpy as np
from scipy.linalg import block_diag
from contrast import contrast_score


def test_correlated_dense_replay_and_constant_invariance():
    rng=np.random.default_rng(13); sizes=[4,7,3]; n=sum(sizes)
    groups=np.repeat(np.arange(3),sizes)
    y=rng.normal(size=n); features=rng.normal(size=(n,5)); variance=rng.uniform(.5,2,n)
    c=block_diag(*(np.linalg.qr(np.ones((s,1)),mode='complete')[0][:,1:].T for s in sizes))
    k=np.diag(variance)+features@features.T
    cy=c@y; ck=c@k@c.T
    expected=cy@np.linalg.solve(ck,cy)+np.linalg.slogdet(ck)[1]+len(cy)*np.log(2*np.pi)
    np.testing.assert_allclose(contrast_score(y,features,variance,groups),expected,atol=1e-10)
    np.testing.assert_allclose(contrast_score(y+np.array([4,-7,11])[groups],features,variance,groups),expected,atol=1e-10)
    # Group-constant correlated calibration uncertainties must cancel too.
    f2=np.column_stack((features,np.eye(3)[groups]*300))
    np.testing.assert_allclose(contrast_score(y,f2,variance,groups),expected,atol=1e-7)


def test_empty_contrast_space():
    assert contrast_score(np.ones(2),np.ones((2,1)),np.ones(2),np.arange(2))==0
