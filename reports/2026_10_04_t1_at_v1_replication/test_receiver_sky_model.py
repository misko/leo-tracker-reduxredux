import numpy as np
import pytest

from receiver_sky_model import (directions, disk_grid, sky_xy, prepare, kernel,
                                design, softmax_loss, fit_softmax, softmax_map)
from collect_receiver_sky import compatible, pair_category


def events():
    result=[]
    for s in range(6):
        for side,az in enumerate((270,90)):
            for j in range(25):
                u=directions(az,55+j*.1)
                result.append(dict(scan=f'N{s}',satellite=side,time_s=j*5+.2,
                    channel=1+j%4,outcome=side,east=u[0],north=u[1],up=u[2]))
    return result


def test_cardinal_and_zenith():
    u=directions([0,90,180,270,0],[0,0,0,0,90])
    np.testing.assert_allclose(u,[[0,1,0],[1,0,0],[0,-1,0],[-1,0,0],[0,0,1]],atol=1e-15)
    np.testing.assert_allclose(sky_xy(u),u[:,:2],atol=1e-15)
    _,_,inside,grid=disk_grid(11)
    assert grid.shape==(inside.sum(),3)
    np.testing.assert_allclose(np.linalg.norm(grid,axis=1),1,atol=1e-14)


@pytest.mark.parametrize('field', ['channel','edge','rf_hz','start_counter'])
def test_only_same_observing_opportunity(field):
    p=dict(channel=1,edge='upper',rf_hz=10e9,start_counter=100)
    assert compatible(p,p)
    q=dict(p);q[field]='different'
    assert not compatible(p,q)


def test_uncertain_peer_is_not_a_negative():
    keys=[(1,0,0),(1,1,0)]
    d={keys[0]:{7}}
    assert pair_category(7,keys,d,{},set())==0
    assert pair_category(7,keys,d,{keys[1]:{7}},set()) is None
    assert pair_category(7,keys,d,{}, {keys[1]}) is None
    d[keys[1]]={7}
    assert pair_category(7,keys,d,{}, {keys[1]})==2
    assert pair_category(8,keys,d,{},set()) is None


def test_scan_and_encounter_balancing_duplicate_invariance():
    data=prepare(events()); duplicate=prepare(events()*3)
    assert np.all(data['weight']>0)
    sums=np.bincount(data['scan'],weights=data['weight'])
    np.testing.assert_allclose(sums,sums[0])
    grid=directions([270,90,0],[56,56,10])
    a=kernel(data,grid,bootstrap=20);b=kernel(duplicate,grid,bootstrap=20)
    np.testing.assert_allclose(a['probability'],b['probability'],atol=1e-12,equal_nan=True)
    np.testing.assert_array_equal(a['supported'],[True,True,False])
    assert a['probability'][0,0]>.99 and a['probability'][1,1]>.99
    assert np.isnan(a['probability'][2]).all()
    np.testing.assert_allclose(a['probability'][:2].sum(axis=1),1)


def test_softmax_gradient():
    data=prepare(events());x=design(data['unit'],data['channel'],data['scan'],6)
    rng=np.random.default_rng(3);b=rng.normal(0,.2,x.shape[1]*2);ridge=np.ones(x.shape[1])
    val,g=softmax_loss(b,x,data['outcome'],data['weight'],ridge)
    for i in range(len(b)):
        step=np.eye(len(b))[i]*1e-5
        numeric=(softmax_loss(b+step,x,data['outcome'],data['weight'],ridge)[0]-softmax_loss(b-step,x,data['outcome'],data['weight'],ridge)[0])/2e-5
        np.testing.assert_allclose(g[i],numeric,atol=1e-6,rtol=1e-5)


def test_smooth_model_learns_direction_and_retains_all_rows():
    data=prepare(events());r=fit_softmax(data)
    assert r['converged']
    assert r['in_sample_log_loss']<r['null_log_loss']
    p=softmax_map(r,directions([270,90],[56,56]),6)
    assert p[0,0]>.9 and p[1,1]>.9
    np.testing.assert_allclose(p.sum(axis=1),1)
