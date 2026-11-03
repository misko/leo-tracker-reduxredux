import numpy as np
import pytest

from ds23_family_predictive_selection import family_folds,gaussian_predictive,qualified_gain


def test_whole_family_holdout_has_no_same_family_on_any_receiver():
    labels=np.repeat([2,4,6,8],[30,40,25,20]);keep=np.ones(len(labels),bool)
    folds=family_folds(labels,keep)
    assert [f['family'] for f in folds]==[4,2]
    for fold in folds:
        assert not np.any(fold['train']&fold['test'])
        np.testing.assert_array_equal(fold['train']|fold['test'],keep)
        assert not np.any(labels[fold['train']]==fold['family'])


def test_prediction_matches_direct_dense_gaussian_and_keeps_unseen_modes():
    a=np.array([[1.,0.,.2],[0.,1.,-.3],[1.,1.,.5]])
    u=np.array([[1.,.4,1.],[.3,1.,2.]])
    w=np.array([2.,3.,1.]);prior=np.array([0.,0.,1.]);sigma=np.array([.3,.7]);raw=np.array([.5,-.4])
    got=gaussian_predictive(raw,u,a,w,prior,sigma)
    cov=np.diag(sigma**2)+u@np.linalg.inv(np.diag(prior)+a.T@(w[:,None]*a))@u.T
    expected=raw@np.linalg.solve(cov,raw)+np.linalg.slogdet(cov)[1]+2*np.log(2*np.pi)
    assert got['negative_twice_log_density']==pytest.approx(expected,abs=1e-12)
    other=gaussian_predictive(raw*10,u,a,w,prior,sigma)
    np.testing.assert_allclose(other['marginal_sigma_hz'],got['marginal_sigma_hz'])


def test_two_independent_family_predictions_must_both_improve():
    assert qualified_gain([{'qualified_training':True,'gain':2.}]*2)
    assert not qualified_gain([{'qualified_training':True,'gain':20.},{'qualified_training':True,'gain':-1.}])
    assert not qualified_gain([{'qualified_training':False,'gain':20.}]*2)
    with pytest.raises(ValueError):gaussian_predictive(np.zeros(1),np.zeros((1,1)),np.zeros((1,1)),np.zeros(1),np.ones(1),np.ones(1))
