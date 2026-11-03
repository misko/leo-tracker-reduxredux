import numpy as np
from ds23_conditioned_relative_nomination import gaussian_prediction,refine_prediction,unresolved_curve_score


def test_predictive_score_matches_dense_correlated_Gaussian():
    rng=np.random.default_rng(293);u=rng.normal(size=(13,3));a=rng.normal(size=(3,3));cov=a@a.T+np.eye(3)
    y=rng.normal(size=13);sigma=np.linspace(.4,1.,13);r=gaussian_prediction(y,u,cov,sigma)
    dense=np.diag(sigma**2)+u@cov@u.T
    expected=y@np.linalg.solve(dense,y)+np.linalg.slogdet(dense)[1]+len(y)*np.log(2*np.pi)
    assert abs(r['objective']-expected)<1e-10
    np.testing.assert_allclose(r['parameter_update'],cov@u.T@np.linalg.solve(dense,y),atol=1e-10)


def test_unused_Gaussian_candidate_coordinates_integrate_to_one():
    u=np.arange(12).reshape(6,2)/10;y=np.linspace(-1,1,6)
    a=gaussian_prediction(y,u,np.eye(2),1.)
    b=gaussian_prediction(y,np.pad(u,((0,0),(0,4))),np.eye(6),1.)
    assert abs(a['objective']-b['objective'])<1e-12


def test_absolute_prior_does_not_shift_during_phase_refresh():
    t=np.linspace(-1,1,40);mean=np.array([.4,-.2,0.]);sd=np.array([2.,3.])
    design=np.column_stack((t,t*t,np.ones(len(t))))
    def geometry(reference):
        return dict(intercept=t**3,features=design,elevation=np.ones(len(t))*20)
    y=t**3+design@np.array([.5,-.1,.2])
    a=refine_prediction(y,geometry,mean,np.eye(3),sd,1.,rounds=1)
    b=refine_prediction(y,geometry,mean,np.eye(3),sd,1.,rounds=5)
    np.testing.assert_allclose(a['coefficient'],b['coefficient'],atol=1e-12)
    assert a['score']==b['score']


def test_unresolved_smooth_curve_score_has_no_geographic_coordinate():
    t=np.linspace(5,30,30);y=2000+20*t-3*t*t
    assert np.isfinite(unresolved_curve_score(t,y,20.))
