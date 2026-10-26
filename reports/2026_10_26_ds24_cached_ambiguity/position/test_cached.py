"""Exact state, read-only cache, live receiver geometry and density invariants."""
from copy import deepcopy
import numpy as np
import pytest
import geometry_cache as gc
import cached_policy as p


def candidate():
    knots=np.array([-20.,0.,20.]);velocity=np.array([2.,-5.,4.])
    position=np.array([-3000.,-4000.,5500.])[None]+knots[:,None]*velocity
    modes=np.arange(27,dtype=float).reshape(3,3,3)*.01
    return dict(target_track=dict(times=np.array([-.2,.3]),rf_hz=11.6e9),
        target=dict(observation_ids=['a','b']),
        target_sky=dict(time_s=knots,position_km=position[None],velocity_km_s=np.broadcast_to(velocity,(1,3,3)).copy()),
        target_mode_bank=dict(time_s=knots,position_km=modes,velocity_km_s=modes*.001))


def test_exact_geometry_live_receiver_and_readonly_states(tmp_path):
    c=candidate();nodes=np.array([-.7,0.,.8]);cache=gc.StateCache(tmp_path)
    key,meta=cache.build(c,nodes)
    assert not cache.open(key).flags.writeable
    with pytest.raises(ValueError):cache.open(key)[0,0,0,0,0]=0
    for x in [np.zeros(2),np.array([-10.,10.]),np.array([10.,-10.])]:
        got=cache.geometry(key,x,0,len(nodes));expected=p.base.k.m.q.phase_geometry(c,x,nodes)
        for name,tolerance in [('frequency_hz',2e-8),('shape_columns_hz',2e-8),('elevation_deg',2e-11)]:
            np.testing.assert_allclose(got[name],expected[name],rtol=0,atol=tolerance)
    first=cache.geometry(key,[0,0],0,3);second=cache.geometry(key,[10,10],0,3)
    assert np.max(abs(first['frequency_hz']-second['frequency_hz']))>1
    with pytest.raises(FileExistsError):cache.build(c,nodes)


def test_cache_keys_bind_all_bank_time_native_phase_and_code_inputs():
    c=candidate();nodes=np.array([-.7,0,.8]);key,meta=gc.identity(c,nodes)
    changed=deepcopy(c);changed['target_mode_bank']['position_km'][0,0,0]+=1e-8
    assert gc.identity(changed,nodes)[0]!=key
    changed=deepcopy(c);changed['target_track']['times'][0]+=.01
    assert gc.identity(changed,nodes)[0]!=key
    changed=deepcopy(c);changed['target']['observation_ids'].reverse()
    assert gc.identity(changed,nodes)[0]!=key
    assert gc.identity(c,nodes+.0001)[0]!=key
    assert 'parent_coefficients' not in str(meta) and 'covariance' not in str(meta)


def test_cached_physical_matches_unchanged_full_density_q_and_aliases(tmp_path,monkeypatch):
    c=candidate();nodes=np.linspace(-1,1,11);logs=np.full(11,-np.log(11))
    cache=gc.StateCache(tmp_path);key,_=cache.build(c,nodes);monkeypatch.setattr(p,'CACHE',cache)
    comp=dict(x=np.zeros(2),raw=np.array([100.,110.]),q=np.array([.95,1.02]),
        covariance=np.array([[500.,100.],[100.,800.]]),shifts=np.arange(-4,5)[:,None]*np.ones((9,2))*p.base.k.PERIOD)
    got=p.cached_physical(c,comp,nodes,logs,key);expected=p.base.physical(c,comp,nodes,logs)
    assert got['objective']==pytest.approx(expected['objective'],abs=1e-6)
    assert got['node_min_elevation_deg']==pytest.approx(expected['node_min_elevation_deg'],abs=2e-11)


def test_target_component_and_original_solver_methods_are_not_reimplemented():
    assert p.CachedTarget.component is p.OriginalTarget.component
    assert p.base.fit_method.__code__.co_filename==str(p.PRIOR/'policy.py')
    assert p.base.FIT_SECONDS==60. and p.base.ORDER==16
    assert p.TOL['objective']==1e-6 and p.TOL['gradient_per_km']==1e-5
