import copy
from types import SimpleNamespace

import numpy as np
import pytest

import ds23_family_partition as partition
import probe_ds23_family_cavity_nominations as single
from ds23_family_cavity import predictive_density_reference


def synthetic(monkeypatch):
    def geometry(bank,times,latitude,longitude,phase_seconds):
        j=int(bank['position_km'][0,0,0]);t=np.asarray(times)
        f=100*j+(1+.1*j)*t+.012*t*t+(2+.05*t)*phase_seconds
        return f[None,:],np.full((1,len(t)),35.)
    monkeypatch.setattr(partition,'phase_frequency_grid',geometry)
    monkeypatch.setattr(single,'phase_frequency_grid',geometry)
    monkeypatch.setattr(single,'build_modes',lambda *args:(None,None))
    p=SimpleNamespace(labels=[0,1],supported=[],rows=[dict(candidate_index=0),dict(candidate_index=1)],
        slices=[slice(0,4),slice(4,8)],keep=np.array([False]*4+[True]*4))
    rng=np.random.default_rng(31);a=rng.normal(size=(4,4));cov=a@a.T*.04+np.eye(4)*.2
    times=np.array([1.,2.,3.,4.,9.,10.,11.,12.]);groups=np.repeat([0,1],4)
    radio=np.column_stack([np.ones(8),times/10]);members=[dict(kind='curved',receiver=1,channel=1),dict(kind='curved',receiver=1,channel=1)]
    d=dict(scan=SimpleNamespace(sky=dict(time_s=np.array([0.,20.]),position_km=np.arange(3.)[:,None,None]*np.ones((3,2,3)),
        velocity_km_s=np.zeros((3,2,3))),norads=np.array([100,101,102])),x=np.zeros(2),all_means=np.array([.1,-.2,.3]),widths=np.ones(3))
    data=dict(p=p,radio_width=2,coefficient=np.array([3.,-.4,.1,-.2]),covariance=cov,times=times,
        values=104+1.1*times+.012*times*times,q=np.ones(8),radio=radio,noise=np.full(8,2.),groups=groups,
        members=members,target=0,held_owners=1)
    return d,data


@pytest.mark.parametrize('candidate',[0,1,2])
def test_one_satellite_limit_matches_previous_correlated_predictor(monkeypatch,candidate):
    d,data=synthetic(monkeypatch);aliases=np.zeros(2,int)
    expected=single.candidate_prediction(d,data,candidate,aliases)
    actual=partition.prediction(d,data,[candidate,candidate],aliases)
    for field in ['score','residual_hz','coefficient','prior_mean','prior_covariance']:
        np.testing.assert_allclose(actual[field],expected[field],rtol=1e-12,atol=1e-10)
    np.testing.assert_allclose(actual['phase_s'],[expected['phase_s']],atol=1e-12)
    assert actual['qualified']==expected['qualified']


def test_two_satellite_density_keeps_cross_group_calibration_covariance(monkeypatch):
    d,data=synthetic(monkeypatch);result=partition.prediction(d,data,[0,2],[0,0])
    t=data['times'];u=np.zeros((8,6));u[:,:2]=data['radio'];u[:4,2]=2+.05*t[:4];u[4:,3]=2+.05*t[4:]
    u[np.arange(8),4+data['groups']]=1
    nominal=np.where(data['groups']==0,.0,200.)+(1+.2*(data['groups']==1))*t+.012*t*t
    raw=data['values']-nominal-u@result['prior_mean']
    expected,_=predictive_density_reference(raw,u,result['prior_covariance'],data['noise'])
    assert abs(result['score']-expected)<1e-8
    np.testing.assert_allclose(result['prior_covariance'][:2,:2],data['covariance'][:2,:2])
    total=np.diag(data['noise']**2)+u@result['prior_covariance']@u.T
    assert np.linalg.norm(total[:4,4:])>0
    assert len(result['coefficient'])==6  # one radio pair, two phases, two constants
    assert result['shared_radio_posterior_once']


def test_partitions_need_curved_evidence_on_both_sides_and_deduplicate_complements():
    tracks=[dict(key='a',receiver=1,channel=1,times=[0.,2.]),dict(key='b',receiver=2,channel=6,times=[4.,6.]),
        dict(key='linear',receiver=1,channel=2,times=[8.,10.])]
    members=[dict(kind='curved',track_index=0),dict(kind='curved',track_index=1),dict(kind='predictive',track_index=2)]
    result=partition.partitions(SimpleNamespace(tracks=tracks),members)
    masks=[tuple(r['member_sides']) for r in result]
    assert len(set(min(m,tuple(1-np.array(m))) for m in masks))==len(masks)
    assert all(len(set(m[:2]))==2 for m in masks)
    assert partition.partitions(SimpleNamespace(tracks=tracks),[members[0],members[2]])==[]


def test_partial_assignments_preserve_original_rows_inactive_aliases_and_predictive_points():
    tracks=[dict(key='a',receiver=1,channel=1,times=[1.,2.]),dict(key='b',receiver=2,channel=1,times=[1.,2.]),
        dict(key='inactive',receiver=2,channel=6,times=[4.,5.]),dict(key='linear',receiver=1,channel=2,times=[3.,4.])]
    rows=[dict(component=t['key'],candidate_index=0,candidate_norad=100) for t in tracks[:3]]
    entry=dict(component='linear',candidate_index=0,norad=100,alias=0,observation_ids=['a','b'],points=2)
    d=dict(scan=SimpleNamespace(tracks=tracks,norads=np.array([100,101,102])),node=dict(seed=dict(rows=rows),aliases=[0,0,1]),
        entries=[entry],all_means=np.array([.1,.2,.3]))
    family=dict(original_index=0,members=[dict(component='a'),dict(component='b'),dict(component='linear')])
    offer=dict(pair=[1,2],partition=dict(kind='receiver',receiver=1),labels_by_member=[1,2,1],aliases=[-1,1,2])
    before=copy.deepcopy((d['node'],d['entries']))
    node,entries,means=partition.configuration(d,[(family,offer)])
    assert [r['candidate_index'] for r in node['seed']['rows']]==[1,2,2]
    assert node['aliases']==[-1,1,1]
    assert entries[0]['candidate_index']==1 and entries[0]['alias']==2
    assert entries[0]['observation_ids']==['a','b'] and entries[0]['points']==2
    assert (d['node'],d['entries'])==before
    np.testing.assert_array_equal(means,[.2,.3])
    with pytest.raises(ValueError,match='duplicate'):partition.configuration(d,[(family,offer),(family,offer)])


def test_subset_screen_remaps_disjoint_fragment_indices_before_alias_selection(monkeypatch):
    from probe_ds23_family_partition import coarse_subset
    from ds23_family_cavity import coarse_phase_scores
    d,data=synthetic(monkeypatch)
    d['widths']=d['widths'][:2]
    data['groups']=np.array([0,0,1,1,2,2,3,3]);data['base_covariance']=np.eye(8)*4
    mask=np.isin(data['groups'],[0,2]);f=np.stack([np.ones(8)*100,np.ones(8)*200]);derivative=np.ones_like(f)
    coarse,original_groups=coarse_subset(d,data,mask,f,derivative,np.ones_like(f)*30)
    np.testing.assert_array_equal(original_groups,[0,2])
    expected=coarse_phase_scores(data['values'][mask],(data['radio']@data['coefficient'][:2])[mask],
        f[:,mask],derivative[:,mask],d['widths'][:2],np.eye(4)*4,np.array([0,0,1,1]))
    # Both independent candidate lists contain exactly two phase widths.
    np.testing.assert_allclose(coarse['score'],expected['score'])
    assert coarse['aliases'].shape==(2,2)
