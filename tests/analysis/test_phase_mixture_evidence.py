import numpy as np
import pytest
from scipy.special import logsumexp
from leo.analysis.research.predictive_track import condition_coefficients,phase_mixture_evidence,gaussian_log_density


def test_low_rank_phase_integration_matches_dense_joint_gaussians():
    rng=np.random.default_rng(312);y=rng.normal(size=7);means=rng.normal(size=(5,7));u=rng.normal(size=(5,7,3))
    h=rng.normal(size=(7,4));base=np.eye(7)*2+h@h.T;lp=np.log([.1,.2,.15,.3,.25]);visible=np.array([1,0,1,1,0],bool)
    r=phase_mixture_evidence(y,means,base,u,lp,visible)
    density=np.array([gaussian_log_density(y-m,base+v@v.T) for m,v in zip(means,u,strict=True)])
    assert r['negative_twice_log_density']==pytest.approx(-2*logsumexp((lp+density)[visible]))
    np.testing.assert_allclose(r['component_log_density'],density)
    for k in range(5):
        expected=u[k].T@np.linalg.solve(base+u[k]@u[k].T,y-means[k])
        np.testing.assert_allclose(r['orbital_posterior_mean'][k],expected)
    assert r['visible_prior_mass']==pytest.approx(.55)


def test_invisible_phase_mass_is_penalized_not_renormalized():
    args=(np.ones(3),np.zeros((2,3)),np.eye(3),np.zeros((2,3,1)),np.zeros(2))
    full=phase_mixture_evidence(*args,[True,True]);half=phase_mixture_evidence(*args,[True,False])
    assert half['negative_twice_log_density']-full['negative_twice_log_density']==pytest.approx(2*np.log(2))
    none=phase_mixture_evidence(*args,[False,False]);assert np.isinf(none['negative_twice_log_density'])
    assert not none['phase_weights'].any()


def test_old_predictive_conditioning_preserves_joint_density_and_calibration():
    rng=np.random.default_rng(422);a=rng.normal(size=4);v=rng.normal(size=(4,4));cov=np.eye(4)+v@v.T
    h=rng.normal(size=(9,4));noise=np.eye(9)*2;y=rng.normal(size=9);old=np.arange(9)<5
    saved=a.copy(),cov.copy();mu,c=condition_coefficients(a,cov,h[old],y[old]-h[old]@a,noise[np.ix_(old,old)])
    combined=gaussian_log_density(y-h@a,noise+h@cov@h.T)
    sequential=gaussian_log_density(y[old]-h[old]@a,noise[np.ix_(old,old)]+h[old]@cov@h[old].T)
    sequential+=gaussian_log_density(y[~old]-h[~old]@mu,noise[np.ix_(~old,~old)]+h[~old]@c@h[~old].T)
    assert sequential==pytest.approx(combined)
    np.testing.assert_array_equal(a,saved[0]);np.testing.assert_array_equal(cov,saved[1])
