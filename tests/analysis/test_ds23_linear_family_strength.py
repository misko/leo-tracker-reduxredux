from pathlib import Path
from types import SimpleNamespace
import sys
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'tools'))
import ds23_linear_family_strength as model
from ds23_predictive_linear import predictive_residual


def test_support_uses_only_active_curves_and_strongest_family_evidence():
    rows = [dict(candidate_index=j) for j in [4,4,4,9]]
    strength = model.family_strengths(rows, [slice(i,i+1) for i in range(4)], np.array([True,True,False,True]),
        [.2,.6,1.,.2], [dict(candidate_index=j) for j in [9,4]])
    np.testing.assert_array_equal(strength, [.2,.6])
    with pytest.raises(ValueError, match='no active curved'):
        model.family_strengths(rows, [slice(i,i+1) for i in range(4)], np.array([False]*4),
            [.2,.6,1.,.2], [dict(candidate_index=4)])


def test_supported_prediction_matches_normalized_dense_joint_covariance():
    rng=np.random.default_rng(681); n=17; u=rng.normal(size=(n,4)); a=rng.normal(size=(4,4)); gram=a@a.T+np.eye(4)
    raw=rng.normal(size=n)*50; sigma=rng.uniform(30,60,n); groups=np.arange(n)%3; strength=np.array([.2,.6,1.])
    result=model.supported_prediction(raw,u,gram,sigma,groups,strength)
    bias=np.eye(3)[groups]*300
    covariance=np.diag(2*sigma**2/strength[groups])+u@np.linalg.solve(gram,u.T)+bias@bias.T
    expected=raw@np.linalg.solve(covariance,raw)+np.linalg.slogdet(covariance)[1]+n*np.log(2*np.pi)
    assert result['objective']==pytest.approx(expected,rel=1e-12,abs=1e-10)
    np.testing.assert_allclose(np.diag(covariance-bias@bias.T-u@np.linalg.solve(gram,u.T)),2*sigma**2/strength[groups],rtol=1e-13)


def test_unit_strength_exactly_reproduces_original_predictive_density():
    rng=np.random.default_rng(18);u=rng.normal(size=(12,3));raw=rng.normal(size=12);s=np.full(12,40.);g=np.arange(12)%2
    a=model.supported_prediction(raw,u,np.eye(3),s,g,np.ones(2))
    b=predictive_residual(raw,u,np.eye(3),s*np.sqrt(2),g)
    assert a['objective']==b['objective']
    np.testing.assert_array_equal(a['residual'],b['residual'])


def test_prediction_does_not_update_curved_coefficients_or_shared_covariance(monkeypatch):
    rows=[dict(candidate_index=7)];entries=[dict(candidate_index=7)]
    coefficients=np.array([.4,-.2]);features=np.array([[1.,2.],[2.,-1.]])
    curved_result=dict(coefficient=coefficients.copy(),features=features.copy(),noise_precision=np.array([.8]),
        coefficient_prior_precision=np.array([1.,2.]),negative_twice_elbo=10.,normalization_constant=3.,residual=np.ones(3))
    def curved(_): return {k:v.copy() if isinstance(v,np.ndarray) else v for k,v in curved_result.items()}
    p=SimpleNamespace(rows=rows,slices=[slice(0,2)],keep=np.ones(2,bool),noise_groups=np.zeros(2,int),
        point_noise=np.full(2,40.),calculate=curved)
    view=SimpleNamespace(q=np.ones(2));linear_features=np.array([[.5,1.],[1.,.3]])
    monkeypatch.setattr(model,'linear_geometry',lambda *_:(view,np.array([90.,80.]),np.full(2,40.),np.zeros(2,int),[slice(0,2)]))
    monkeypatch.setattr(model,'geometry_features',lambda *_:dict(features=linear_features,intercept=np.ones(2)*30,elevation=np.ones(2)*40))
    model.attach_supported_prediction(p,entries,np.array([.2]));r=p.calculate(np.zeros(2))
    np.testing.assert_array_equal(r['coefficient'],coefficients)
    np.testing.assert_array_equal(r['coefficient_prior_precision'],curved_result['coefficient_prior_precision'])
    np.testing.assert_array_equal(r['linear_raw_prediction_residual_hz'],np.array([90.,80.])-30-linear_features@coefficients)
    assert r['linear_calibration_coefficient_unchanged']


@pytest.mark.parametrize('strength',[[0.],[-1.],[1.1],[np.nan],[]])
def test_invalid_support_cannot_silently_remove_or_strengthen_observations(strength):
    with pytest.raises(ValueError): model.supported_prediction(np.ones(2),np.ones((2,1)),np.eye(1),np.ones(2),np.zeros(2,int),np.array(strength))
