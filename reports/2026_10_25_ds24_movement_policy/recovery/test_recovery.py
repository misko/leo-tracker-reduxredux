import copy
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

import recovery as r
from ds23_active_mode_support import disabled_families


def test_RF_ranking_ignores_error_fields_and_breaks_ties_by_case():
    def row(case,value,error):
        return dict(case=case,error_km=error,arms={'c0':{'curved':{'all':{'principal_sigma_km':[value]}}}})
    rows=[row('C',1,100),row('B',2,0),row('A',2,1000)]
    assert [v['case'] for v in r.ranked_cases({'rows':rows})]==['A','B','C']


def test_whole_target_excludes_any_parent_ID_in_either_arm():
    tracks=[dict(key=f't{k}',observation_ids=[f'{k}a',f'{k}b'],times=np.array([0.,30.-k]),receiver=1,channel=1) for k in range(3)]
    base=SimpleNamespace(rows=[{}]*3,members=[0,1,2],slices=[slice(0,2),slice(2,4),slice(4,6)])
    d=dict(base=base,keep=np.zeros(6,bool),scan=SimpleNamespace(tracks=tracks,curved=[0,1,2]))
    inv=r.target_inventory(d,{'c0':{'accepted_observation_ids':['0a']},'fitted_c':{'accepted_observation_ids':['1b']}})
    assert [v['component'] for v in inv['ranking']]==['t2']
    assert len(inv['excluded'])==2


def test_rescue_trigger_is_original_gate_failure_and_near_feasible_only():
    assert r.rescue_eligible(False,[-.25,.1])
    assert not r.rescue_eligible(False,[-.250001,.1])
    assert not r.rescue_eligible(True,[-.1])
    assert not r.rescue_eligible(False,[])


def test_rescue_preserves_ordinary_endpoint_before_modification(monkeypatch,tmp_path):
    def make():
        return dict(phase_reference=[0.],endpoint_east_north_km=[1.,2.],negative_twice_elbo=10.,final_phase_change_s=.001)
    monkeypatch.setattr(r,'refit',lambda *args:make())
    monkeypatch.setattr(r,'valid',lambda pair:pair['c0']['endpoint_east_north_km'][0]==3.)
    monkeypatch.setattr(r,'gate_slacks',lambda *args:{'rms':-.1})
    monkeypatch.setattr(r,'unused_count',lambda *args:0)
    p=SimpleNamespace(calculate=lambda x:{'coefficient':np.zeros(1)})
    monkeypatch.setattr(r,'build',lambda *args:p)
    def constrain(*args):
        pair=args[-1]
        for value in pair.values():value['endpoint_east_north_km'][0]=3.
        return pair
    monkeypatch.setattr(r,'constrained',constrain)
    d=dict(scan=None,keep=[],powers=[],model={'nu':3.})
    out=r.fit_record(d,{},[],[],tmp_path/'ordinary.json')
    assert out['ordinary_arms']['c0']['endpoint_east_north_km']==[1.,2.]
    assert out['rescued_arms']['c0']['endpoint_east_north_km']==[3.,2.]
    assert r.read(tmp_path/'ordinary.json')['ordinary_arms']['c0']['endpoint_east_north_km']==[1.,2.]
    assert out['paired_valid']


def test_loss_of_parent_ID_or_incumbent_shape_mode_forces_rejection():
    def row(ids,modes):
        return dict(accepted_observation_ids=ids,curved_observation_ids=ids,predictive_observation_ids=[],supported_families=modes)
    parent={a:row(['a','b'],[4]) for a in r.ARMS}
    child={a:row(['a','b','c'],[4,5]) for a in r.ARMS}
    modes={a:[4] for a in r.ARMS}
    assert r.preserved(r.preserve_parent(parent,child,modes))
    child['fitted_c']['accepted_observation_ids']=['a','c']
    assert not r.preserved(r.preserve_parent(parent,child,modes))
    child={a:row(['a','b','c'],[5]) for a in r.ARMS}
    assert not r.preserved(r.preserve_parent(parent,child,modes))


def test_support_controls_keep_incumbents_and_disable_only_new_one_owner_family():
    rows=[dict(candidate_index=j) for j in (1,1,2,2)]
    tracks=[dict(receiver=rx,channel=1) for rx in (1,2,1,2)]
    sl=[slice(k,k+1) for k in range(4)]
    assert disabled_families([1,2],rows,sl,list(range(4)),tracks,np.array([True,False,True,False]),{1})==[2]


def test_no_overwrite_and_tampered_protocol_seal_rejected(monkeypatch,tmp_path):
    path=tmp_path/'protocol.json';r.write_new(path,{'input_sha256':{},'source_sha256':{}})
    with pytest.raises(FileExistsError):r.write_new(path,{})
    monkeypatch.setattr(r,'HERE',tmp_path)
    r.write_new(tmp_path/'protocol_seal.json',{'protocol_sha256':r.sha(path)})
    assert r.verify()['input_sha256']=={}
    path.write_text('{}')
    with pytest.raises(ValueError,match='seal changed'):r.verify()


def test_existing_configuration_controls_do_not_invent_identity_or_trim_source():
    def target(k,old,best):
        return dict(row_index=k,original={'candidate_index':old},best=None if best is None else {'candidate_index':best})
    configs=r.single.configurations({'targets':[target(0,1,1),target(1,2,3),target(2,4,None)]})
    assert len(configs)==5
    assert configs[-1][0][1]['candidate_index']==4
    assert any(len(c)==1 and c[0][0]['row_index']==1 and c[0][1]['candidate_index']==2 for c in configs)
