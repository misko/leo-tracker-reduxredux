import numpy as np
from ds23_predictive_linear import predictive_residual,attach_predictive_linear


def test_shared_calibration_uncertainty_matches_dense_predictive_covariance():
    rng=np.random.default_rng(12);u=rng.normal(size=(9,3));y=rng.normal(size=9)
    a=rng.normal(size=(3,3));gram=a.T@a+np.eye(3);sigma=np.linspace(.7,1.4,9)
    groups=np.repeat(np.arange(3),3);bias=1.3
    c=np.diag(sigma*sigma)+u@np.linalg.solve(gram,u.T)+bias*bias*(groups[:,None]==groups)
    expected=y@np.linalg.solve(c,y)+np.linalg.slogdet(c)[1]+len(y)*np.log(2*np.pi)
    result=predictive_residual(y,u,gram,sigma,groups,bias)
    np.testing.assert_allclose(result['objective'],expected,rtol=1e-12)


def test_identical_samples_do_not_make_shared_calibration_uncertainty_independent():
    gram=np.array([[.25]])
    r=predictive_residual(np.ones(20),np.ones((20,1)),gram,np.ones(20),np.zeros(20,int),.01)
    independent=20/(1+4+.0001)
    assert r['quadratic']<independent/10


def test_empty_extension_preserves_curved_calibration_object():
    p=object()
    assert attach_predictive_linear(p,[],None) is p


def test_linear_evidence_cannot_update_curved_calibration_posterior(monkeypatch):
    from types import SimpleNamespace
    import ds23_predictive_linear as module
    p=SimpleNamespace(noise_groups=np.array([0,0]),keep=np.ones(2,bool),point_noise=np.ones(2))
    def curved(_):
        return dict(features=np.ones((2,1)),noise_precision=np.ones(1),coefficient_prior_precision=np.ones(1),
            coefficient=np.array([2.]),negative_twice_elbo=7.,normalization_constant=3.,residual=np.array([1.,2.]))
    p.calculate=curved
    view=SimpleNamespace(q=np.ones(3));measurements=np.full(3,100.)
    monkeypatch.setattr(module,'linear_geometry',lambda *a:(view,measurements,np.ones(3),np.zeros(3,int),[slice(0,3)]))
    monkeypatch.setattr(module,'geometry_features',lambda *a:dict(intercept=np.zeros(3),features=np.ones((3,1)),elevation=np.ones(3)))
    attach_predictive_linear(p,[dict()],np.ones(1))
    result=p.calculate(np.zeros(2))
    np.testing.assert_array_equal(result['coefficient'],np.array([2.]))
    np.testing.assert_array_equal(result['linear_raw_prediction_residual_hz'],np.full(3,98.))
    assert result['negative_twice_elbo']>result['curved_negative_twice_elbo']==7.
    np.testing.assert_array_equal(p.curved_calculate(np.zeros(2))['coefficient'],result['coefficient'])
