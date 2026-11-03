import itertools
import numpy as np
import pytest

from ds23_soft_predictive_identity import whiten_bias,identity_bound
from ds23_predictive_reassociation import block_objective


def test_track_bias_whitening_matches_dense_covariance():
    rng=np.random.default_rng(391);y=rng.normal(size=9);u=rng.normal(size=(9,3));s=rng.uniform(.5,2,9)
    result=whiten_bias(y,u,s,2.)
    covariance=np.diag(s*s)+4.;inverse=np.linalg.inv(covariance)
    np.testing.assert_allclose(result['gram'],u.T@inverse@u,atol=1e-12)
    np.testing.assert_allclose(result['rhs'],u.T@inverse@y,atol=1e-12)
    assert result['quadratic']==pytest.approx(y@inverse@y,abs=1e-12)
    assert result['normalization']==pytest.approx(np.linalg.slogdet(covariance)[1]+len(y)*np.log(2*np.pi),abs=1e-12)


def random_blocks():
    rng=np.random.default_rng(227)
    return [[dict(raw=rng.normal(size=5),uncertainty=rng.normal(size=(5,2)),sigma=rng.uniform(.5,2,5)) for _ in range(2)] for _ in range(3)]


def sufficient(pools):
    return [[whiten_bias(b['raw'],b['uncertainty'],b['sigma'],.8) for b in p] for p in pools]


def test_one_hot_limit_matches_exact_joint_density_and_preserves_shared_covariance():
    pools=random_blocks();stats=sufficient(pools);priors=[np.array([1.,0.]),np.array([0.,1.]),np.array([1.,0.])]
    result=identity_bound(stats,priors=priors)
    exact=block_objective([pools[0][0],pools[1][1],pools[2][0]],bias_sigma_hz=.8)
    assert result['objective']==pytest.approx(exact,abs=1e-10)
    assert result['residual']@result['residual']+result['normalization_constant']==pytest.approx(exact,abs=1e-10)


def test_variational_identity_bound_is_conservative_against_exact_enumeration():
    pools=random_blocks();result=identity_bound(sufficient(pools),maximum_iterations=200,tolerance=1e-10)
    costs=np.array([block_objective([pool[j] for pool,j in zip(pools,choice,strict=True)],bias_sigma_hz=.8) for choice in itertools.product(range(2),repeat=3)])
    low=costs.min();exact=low-2*np.log(np.exp(-.5*(costs-low)).mean())
    assert result['objective']>=exact-1e-10
    assert result['converged']
    assert all(b<=a+1e-10 for a,b in zip(result['history'][:-1],result['history'][1:],strict=True))
    assert all(abs(w.sum()-1)<1e-12 for w in result['weights'])


def test_zero_calibration_uncertainty_has_exact_independent_identity_marginals():
    raw=[np.array([1.,2.]),np.array([-.2,.1])]
    pools=[[whiten_bias(r,np.empty((2,0)),np.ones(2),.8) for r in raw] for _ in range(2)]
    result=identity_bound(pools)
    costs=np.array([b['quadratic']+b['normalization'] for b in pools[0]]);minimum=costs.min()
    exact=2*(minimum-2*np.log(np.exp(-.5*(costs-minimum)).mean()))
    assert result['objective']==pytest.approx(exact,abs=1e-12)


def test_invalid_priors_and_mismatching_inputs_are_rejected():
    with pytest.raises(ValueError):whiten_bias(np.ones(2),np.ones((3,1)),np.ones(2))
    with pytest.raises(ValueError):identity_bound([])
    pools=sufficient(random_blocks())
    with pytest.raises(ValueError):identity_bound(pools,priors=[np.array([1.,1.])]*3)
    with pytest.raises(ValueError):identity_bound(pools,priors=[np.array([1.,0.])]*3,initial=[np.array([0.,1.])]*3)


def test_predictive_identity_updates_never_replace_curved_calibration(monkeypatch):
    from types import SimpleNamespace
    import ds23_predictive_linear as linear
    import ds23_height_problem as geometry
    from ds23_soft_predictive_identity import attach_soft_identities
    p=SimpleNamespace(noise_groups=np.array([0,0]),keep=np.ones(2,bool),point_noise=np.ones(2),
        rows=[dict(candidate_index=0),dict(candidate_index=1)],slices=[slice(0,1),slice(1,2)],
        scan=SimpleNamespace(norads=[100,101],tracks=[dict(times=np.arange(3))]))
    def curved(_):return dict(features=np.ones((2,1)),noise_precision=np.ones(1),coefficient_prior_precision=np.ones(1),
        coefficient=np.array([2.]),negative_twice_elbo=7.,normalization_constant=3.,residual=np.array([1.,2.]))
    p.calculate=curved
    def offered(_,entries):
        n=3*len(entries);view=SimpleNamespace(q=np.ones(n))
        return view,np.full(n,100.),np.ones(n),np.zeros(n,int),[slice(k,k+3) for k in range(0,n,3)]
    monkeypatch.setattr(linear,'linear_geometry',offered)
    monkeypatch.setattr(geometry,'geometry_features',lambda view,*args:dict(intercept=np.zeros(len(view.q)),features=np.ones((len(view.q),1)),elevation=np.ones(len(view.q))))
    entries=[dict(candidate_index=0,norad=100,track_index=0,alias=0)]
    attach_soft_identities(p,entries,np.ones(1));result=p.calculate(np.zeros(2))
    np.testing.assert_array_equal(result['coefficient'],[2.])
    np.testing.assert_array_equal(result['coefficient'],p.curved_calculate(np.zeros(2))['coefficient'])
    np.testing.assert_allclose(result['soft_identity']['weights'][0],[.5,.5],atol=1e-10)
    assert result['linear_calibration_coefficient_unchanged']
