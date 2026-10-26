"""Owned density, scalar-adapter, prior and actual narrow-port invariants."""
import ast
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
from scipy.special import logsumexp
import policy as e


def test_normalized_whole_owner_mixture_and_single_hard():
    assert e.combine([-5.]*8,-5.,'mixture') == pytest.approx(10.)
    assert e.combine([-5.],0.,'hard') == 10.
    assert e.combine([-5.,-6.,-7.,-8.,-9.,-10.,-11.,-12.],-4.,'mixture') == pytest.approx(
        -2*np.log(sum(np.exp(-np.arange(5.,13.)))*.5/8+np.exp(-4)*.5))


def test_positive_woodbury_matches_dense_all_aliases():
    rng=np.random.default_rng(51);n=7;nodes=4
    a=rng.normal(size=(n,n));cov=a@a.T+np.eye(n)*4
    raw=rng.normal(size=(nodes,n));shape=rng.normal(size=(nodes,n,3))
    shifts=np.array([-1.,0.,1.])[:,None]*np.ones((3,n))*4
    got=e.sr.sm.positive_costs(raw,cov,shape,shifts)
    expected=[]
    for y,b in zip(raw,shape,strict=True):
        c=cov+b@b.T;sign,det=np.linalg.slogdet(c);assert sign==1
        expected.append([float((y+s)@np.linalg.solve(c,y+s)+det+n*np.log(2*np.pi)) for s in shifts])
    np.testing.assert_allclose(got,expected,atol=1e-12)


def test_target_adapter_preserves_parent_arrays_offset_and_scalar_increment():
    coef=np.arange(3.);noise=np.array([.8,1.2]);cached=dict(negative_twice_elbo=31.,normalization_constant=8.,
        residual=np.array([2.,3.]),coefficient=coef,noise_precision=noise)
    class Parent:
        def calculate(self,x):return cached
        def residual(self,x):return np.r_[self.calculate(x)['residual'],2.]
    parent=Parent();original=parent.calculate
    target=SimpleNamespace(score=lambda x,method:dict(objective=7.))
    e.attach(parent,target,'mixture')
    for _ in range(3):
        result=parent.calculate(np.zeros(2))
        assert result['negative_twice_elbo']-original(None)['negative_twice_elbo']==7.
        assert np.sum(parent.residual(np.zeros(2))**2)-(np.sum(cached['residual']**2)+4)==pytest.approx(7.)
        assert result['normalization_constant']==cached['normalization_constant']
        np.testing.assert_array_equal(result['coefficient'],coef)
        np.testing.assert_array_equal(result['noise_precision'],noise)
    assert cached['negative_twice_elbo']==31. and len(cached['residual'])==2


def test_no_addition_leaves_exact_original_problem_untouched():
    parent=SimpleNamespace(calculate=lambda x:dict(negative_twice_elbo=31.))
    method=parent.calculate
    assert e.attach(parent,None,'no_addition') is parent
    assert parent.calculate is method


def test_actual_context_and_redacted_unknown_smoke_has_both_matched_arms():
    smoke=e.r.read(e.HERE/'load_smoke04.json')
    assert smoke['all_passed'] and smoke['actual_target_density_evaluations']==0
    assert smoke['source_sha256']==e.r.sha(e.HERE/'smoke_source.py')
    def functions(path):
        return {node.name:ast.dump(node) for node in ast.parse(Path(path).read_text()).body
            if isinstance(node,(ast.FunctionDef,ast.ClassDef)) and node.name!='freeze'}
    assert functions(e.HERE/'smoke_source.py')==functions(e.__file__)
    assert [row['arm'] for row in smoke['checks']]==list(e.ARMS)
    ids=[]
    for row in smoke['checks']:
        assert len(row['exact20_native_IDs'])==len(set(row['exact20_native_IDs']))==20
        ids.append(row['exact20_native_IDs'])
        assert max(row['errors'].values())<1e-6
        assert row['all8_absent_active'] and row['cavity_removed_IDs']==[]
        assert not row['source_gate']['original_growth_supported']
        assert row['source_gate']['original_target_active_points']==0
        assert np.isfinite(row['redacted_unknown_objective'])
        assert row['full_parent_includes_existing_predictive'] and row['original_predictive_points']>=0
        assert row['scalar_residual_increment']==pytest.approx(7.)
        assert row['full_ELBO_increment']==pytest.approx(7.)
    assert ids[0]==ids[1]


def test_every_piece_rule_original_normalized_prior_and_exact_domain():
    candidate=dict(target_track=dict(times=np.array([.1,.2])),
        target_sky=dict(time_s=np.array([-16.,0.,16.])),target_mode_bank=dict(time_s=np.array([-16.,0.,16.])),
        target=dict(phase_nu=3,phase_mean_s=.4,phase_sd_s=2.))
    nodes,logs=e.rule(candidate,64)
    assert np.all(nodes>-15) and np.all(nodes<15)
    assert abs(np.exp(logsumexp(logs))-1)<2e-4
    candidate['target_mode_bank']['time_s']=np.array([-16.,1.,16.])
    with pytest.raises(ValueError):e.rule(candidate,16)


def test_source_gate_view_does_not_change_original_mask_or_cached_result(monkeypatch):
    keep=np.array([True,False]);cached=dict(value=np.arange(2.));p=SimpleNamespace(
        rows=[dict(component='parent'),dict(component='target')],slices=[slice(0,1),slice(1,2)],
        keep=keep,calculate=lambda x:cached,state=lambda x:{},conditional_frequency=lambda x:None)
    def gate(view,x):
        assert view.keep.all() and not p.keep.all()
        assert view.calculate(x) is cached
        return dict(tracks=[dict(component='target',compatible=True)])
    monkeypatch.setattr(e,'retained_metrics',gate)
    monkeypatch.setattr(e,'growth_supported',lambda parent,offer:False)
    result=e.source_gate({},p,np.zeros(2),dict(component='target',candidate_index=2,observation_ids=['oid']))
    assert not result['original_growth_supported'] and not result['accepted_target']
    np.testing.assert_array_equal(p.keep,[True,False])
    assert p.calculate(None) is cached


def test_control_reproduction_requires_all_frozen_engineering_tolerances():
    saved=dict(endpoint_east_north_km=[1.,2.],negative_twice_elbo=20000.)
    assert e.control_reproduction([1.0005,2.],20000.0001,saved,1e-9)['passed']
    assert not e.control_reproduction([1.002,2.],20000.,saved,0.)['passed']
    assert not e.control_reproduction([1.,2.],20000.0009,saved,0.)['passed']
    assert not e.control_reproduction([1.,2.],20000.,saved,2e-8)['passed']
