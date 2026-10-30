from types import SimpleNamespace
import numpy as np
import pytest
import json
from inactive_graph_fragment import append_inactive_fragment,inactive_fragment_context,validated_inactive_context,original_graph_view


def fixture():
    track=dict(key='parent',observation_ids=['a','b','c','d'],times=np.array([1.,2.,3.,4.]),values=np.array([100.,1100.,-900.,103.]))
    return SimpleNamespace(tracks=[track],white=['unchanged'],rx_basis=[np.arange(12).reshape(4,3)],curved=np.array([0]))


def test_fragment_removes_union_of_owned_points_preserves_values_and_calibration_graph():
    scan=fixture();changed,i=append_inactive_fragment(scan,0,{'a','c'})
    assert i==1 and len(scan.tracks)==1 and changed.tracks[0] is scan.tracks[0]
    assert changed.curved is scan.curved and changed.white[0]=='unchanged'
    assert changed.tracks[i]['observation_ids']==['b','d']
    np.testing.assert_array_equal(changed.tracks[i]['values'],[1100.,103.])
    np.testing.assert_array_equal(changed.tracks[i]['times'],[2.,4.])
    np.testing.assert_array_equal(changed.rx_basis[i],scan.rx_basis[0][[1,3]])
    assert not np.shares_memory(changed.tracks[i]['values'],scan.tracks[0]['values'])


@pytest.mark.parametrize('occupied',[set(),{'a','b','c','d'}])
def test_fragment_requires_partially_owned_parent(occupied):
    with pytest.raises(ValueError,match='partial'):append_inactive_fragment(fixture(),0,occupied)


def test_duplicate_parent_observations_rejected():
    scan=fixture();scan.tracks[0]['observation_ids'][-1]='a'
    with pytest.raises(ValueError,match='repeats'):append_inactive_fragment(scan,0,{'a'})


def test_context_protects_both_arms_and_reconstruction_rejects_changed_ownership(tmp_path):
    scan=fixture();problems={a:(SimpleNamespace(members=[0],slices=[slice(0,4)],keep=np.array(k)),None)
        for a,k in [('c0',[True,False,False,False]),('fitted_c',[False,False,True,False])]}
    d=dict(scan=scan,problems=problems,entries=[])
    inv=dict(job=dict(job_id='job'),tracks=[dict(track_id='tid',track_index=0,current_large=True)],
        policy={a:dict(proposed_associated_ids=[]) for a in problems})
    changed,target=inactive_fragment_context(d,inv,'tid')
    assert target['observation_ids']==['b','d'] and changed['problems'] is problems
    receipt={k:target[k] for k in ('track_id','component','parent_track_index','observation_ids')}
    (tmp_path/'protocol.json').write_text(json.dumps(dict(job=inv['job'],target=receipt)))
    (tmp_path/'result.json').write_text(json.dumps(dict(track_id='tid',inactive_graph_fragment=True)))
    replay,t=validated_inactive_context(d,inv,tmp_path)
    assert t['observation_ids']==['b','d']
    inv['policy']['fitted_c']['proposed_associated_ids']=['b']
    with pytest.raises(ValueError,match='changed'):validated_inactive_context(d,inv,tmp_path)


def test_membership_view_excludes_unindexed_append_without_changing_predictive_problem():
    scan=fixture();changed,i=append_inactive_fragment(scan,0,{'a','c'})
    problem=SimpleNamespace(scan=changed,entries=[dict(track_index=i)])
    view=original_graph_view(problem,1)
    assert len(view.scan.tracks)==1 and len(problem.scan.tracks)==2
    assert view.entries is problem.entries and view.scan.curved is problem.scan.curved
    with pytest.raises(ValueError,match='count'):original_graph_view(problem,3)
