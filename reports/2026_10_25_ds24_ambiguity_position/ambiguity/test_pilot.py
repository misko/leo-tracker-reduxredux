"""Owned prior/conditional-mixture/interval and actual input-port tests."""
import ast
from pathlib import Path
import numpy as np
import pytest
from scipy.special import logsumexp
import pilot as p


def models(objective=10.,width=.1):
    return [dict(objective=objective,certified_visibility=True,
        full_support_lower_log_integral=-.5*(objective+width),full_support_upper_log_integral=-.5*(objective-width)) for _ in range(8)]


def null(objective=12.,width=1e-6):
    return dict(objective=objective,reference_passed=True,lower_logZ=-.5*(objective+width),upper_logZ=-.5*(objective-width))


def test_normalized_whole_owner_mixture_not_eight_unpenalized_copies():
    for weight in p.PHYSICAL_WEIGHTS:
        result=p.mixture(models(10.,0.),null(10.,0.),weight)
        assert result['objective']==pytest.approx(10.)
        assert result['lower_objective']==pytest.approx(10.)
        assert result['upper_objective']==pytest.approx(10.)
        assert sum(result['conditional_model_weights'])==pytest.approx(1.)
        assert not result['weights_are_calibrated_identity_probabilities']


def test_mixture_bounds_contain_independent_enumeration_and_are_monotone():
    rows=models();rows[0].update(objective=9.,full_support_lower_log_integral=-4.7,full_support_upper_log_integral=-4.3)
    for weight in p.PHYSICAL_WEIGHTS:
        result=p.mixture(rows,null(),weight)
        expected=-2*logsumexp(np.r_[-.5*np.array([row['objective'] for row in rows])+np.log(weight/8),-6+np.log(1-weight)])
        assert result['objective']==pytest.approx(expected)
        assert result['lower_objective']<=expected<=result['upper_objective']
    rows[0]['full_support_upper_log_integral']=None
    assert p.mixture(rows,null(),.5)['available']
    assert not p.mixture(rows,null(),.5)['bounds_available']


def test_certified_empty_support_is_exact_zero_not_unknown_integral():
    rows=models();rows[0]=dict(objective=None,empty_support_certified=True,certified_visibility=True)
    result=p.mixture(rows,null(),.5)
    assert result['available'] and result['bounds_available']
    expected=-2*np.log(.5*7/8*np.exp(-5)+.5*np.exp(-6))
    assert result['objective']==pytest.approx(expected)
    rows[0]['empty_support_certified']=False
    assert not p.mixture(rows,null(),.5)['available']


def test_secant_change_interval_and_proxy_sign_dense_endpoint_enumeration():
    hardm=dict(objective=10.,lower_objective=9.9,upper_objective=10.1,bounds_available=True)
    hardp=dict(objective=11.,lower_objective=10.9,upper_objective=11.1,bounds_available=True)
    mixm=dict(objective=9.,lower_objective=8.9,upper_objective=9.1,bounds_available=True)
    mixp=dict(objective=9.5,lower_objective=9.4,upper_objective=9.6,bounds_available=True)
    result=p.secant_difference(mixm,mixp,hardm,hardp,4.)
    assert result['delta_finite_difference_per_km']==pytest.approx(-2.5)
    assert result['archived_c0_curvature_scaled_secant_proxy_km']==pytest.approx(.3125)
    exact=[]
    for a in [9.4,9.6]:
        for b in [10.9,11.1]:
            for c in [8.9,9.1]:
                for d in [9.9,10.1]:exact.append((a-b-c+d)/.2)
    np.testing.assert_allclose(result['delta_finite_difference_interval'],[min(exact),max(exact)])
    assert result['interval_supports_material_25m']
    mixp['bounds_available']=False
    assert not p.secant_difference(mixm,mixp,hardm,hardp,4.)['bounds_available']


def test_fixed_graph_coordinate_unknown_is_independent_of_x_when_radio_is_fixed():
    rng=np.random.default_rng(5);n=12;times=np.linspace(100,130,n)
    comp=dict(raw=rng.normal(size=n)*30,covariance=np.eye(n)*300.,
        d=dict(target_track=dict(times=times)),groups=np.zeros(n,int),x=np.zeros(2))
    comp['aliases'],comp['shifts']=p.k.alias_vectors(comp['groups'],np.arange(-4,5))
    first=p.unknown(comp);second=p.unknown(dict(comp,x=np.array([2.,-3.])))
    assert first['objective']==second['objective']
    assert first['reference_passed'] and first['reference_error']<=1e-7


def test_actual_smoke_covers_all8_nonincumbents_complete_owners_and_common_probes():
    smoke=p.r.read(p.HERE/'load_smoke.json');assert smoke['all_passed'] and smoke['target_density_evaluations']==0
    old=p.HERE/'preparation01/pilot.py'
    assert smoke['source_sha256']==p.r.sha(old)
    def functions(path):return {node.name:ast.dump(node) for node in ast.parse(Path(path).read_text()).body if isinstance(node,ast.FunctionDef)}
    before,after=functions(old),functions(p.__file__)
    for name in ['prepare','context','parent_component','complete_component']:assert before[name]==after[name]
    for case in p.CASES:
        meta=p.r.read(p.HERE/'prepared'/case/'metadata.json')
        assert meta['all8_families_absent_from_parent_likelihood'] and len(meta['pool'])==8
        assert len(set(meta['entry']['observation_ids']))==meta['entry']['points']
        np.testing.assert_allclose(np.array(meta['probes']['plus'])-meta['probes']['minus'],2*p.H*np.array(meta['weak']),atol=1e-14)
        for arm in p.ARMS:
            info=p.r.read(p.HERE/'prepared'/case/(arm+'_parent.json'))
            assert not info['removed_curved_ids'] and not info['removed_predictive_ids'] and p.w.hard_parent(info)
            data=p.arrays(p.HERE/'prepared'/case/(arm+'.npz'))
            np.linalg.cholesky(data['covariance']);assert len(data['raw'])==meta['entry']['points']


def test_parent_objective_cancels_from_model_change_secant():
    first=p.secant_difference(dict(objective=8.),dict(objective=11.),dict(objective=9.),dict(objective=10.),3.)
    second=p.secant_difference(dict(objective=108.),dict(objective=61.),dict(objective=109.),dict(objective=60.),3.)
    assert first['delta_finite_difference_per_km']==second['delta_finite_difference_per_km']
