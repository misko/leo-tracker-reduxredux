"""Native correlated-prior algebra and independent-model identity."""

import numpy as np
from ds23_correlated_orbit_problem import prior_transform, native_posterior


def test_identity_transform_is_exact_original_prior_with_300hz_fragment_scaling():
    t = prior_transform(2, [4,7], [7], 3, np.eye(4))
    np.testing.assert_array_equal(t, np.diag([1.]*7+[.3]*3))


def test_correlation_connects_only_one_family_and_keeps_phase_latent_first():
    c = np.eye(4)
    c[0,1] = c[1,0] = .7
    t = prior_transform(2, [4,7], [7], 3, c)
    native = t@t.T
    indices = [3,4,5,6]
    np.testing.assert_allclose(native[np.ix_(indices,indices)], c)
    assert native[2,4] == 0 and t[3,3] == 1 and np.count_nonzero(t[3]) == 1


def test_native_precision_and_mean_preserve_exact_prior_energy_and_covariance():
    rng=np.random.default_rng(3)
    t=np.eye(5)
    t[1:3,1:3]=np.linalg.cholesky([[1.,.8],[.8,1.]])
    t[-1,-1]=.3
    latent=rng.normal(size=5)
    precision=np.array([1.,2.,1.,1.,1.])
    mean=np.arange(5.)
    coefficient,p=native_posterior(mean,t,latent,precision)
    np.testing.assert_allclose((coefficient-mean)@p@(coefficient-mean), np.sum(latent**2*precision), atol=1e-13)
    np.testing.assert_allclose(np.linalg.inv(p),t@np.diag(1/precision)@t.T, atol=1e-13)
    assert abs(p[1,2]) > .1  # discarding off-diagonals would corrupt prediction.


def test_added_track_prediction_retains_off_diagonal_precision_without_calibration_feedback(monkeypatch):
    from types import SimpleNamespace
    import ds23_correlated_orbit_problem as module
    p=SimpleNamespace(noise_groups=np.array([0,0]),keep=np.ones(2,bool),point_noise=np.ones(2))
    prior=np.array([[2.,1.2],[1.2,2.]])
    coefficient=np.array([1.,2.])
    def curved(_):
        return dict(features=np.eye(2),noise_precision=np.ones(1),coefficient_prior_matrix=prior,
            coefficient=coefficient.copy(),negative_twice_elbo=7.,normalization_constant=3.,residual=np.array([1.,2.]))
    p.calculate=curved
    design=np.array([[1.,0.],[0.,1.],[1.,-1.]])
    measurements=np.array([2.,3.,4.])
    view=SimpleNamespace(q=np.ones(3))
    monkeypatch.setattr(module,"linear_geometry",lambda *args:(view,measurements,np.ones(3),np.zeros(3,int),[slice(0,3)]))
    monkeypatch.setattr(module,"geometry_features",lambda *args:dict(intercept=np.zeros(3),features=design,elevation=np.ones(3)))
    module.attach_correlated_prediction(p,[dict()],np.ones(1))
    result=p.calculate(np.zeros(2))
    covariance=2*np.eye(3)+design@np.linalg.solve(prior+np.eye(2),design.T)+300**2*np.ones((3,3))
    residual=measurements-design@coefficient
    expected=residual@np.linalg.solve(covariance,residual)+np.linalg.slogdet(covariance)[1]+3*np.log(2*np.pi)
    np.testing.assert_allclose(result["linear_predictive_objective"],expected,rtol=1e-10)
    np.testing.assert_array_equal(result["coefficient"],coefficient)
    np.testing.assert_array_equal(result["coefficient"],p.curved_calculate(np.zeros(2))["coefficient"])
