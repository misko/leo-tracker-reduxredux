import copy
from types import SimpleNamespace
import numpy as np
import pytest
from probe_ds23_family_cavity_position import configuration,unused_count


def test_whole_family_relabel_preserves_all_rows_masks_and_predictive_IDs():
    rows=[dict(component='active',candidate_index=1,candidate_norad=101),
          dict(component='inactive',candidate_index=1,candidate_norad=101),
          dict(component='other',candidate_index=2,candidate_norad=102)]
    entry=dict(component='linear',candidate_index=1,norad=101,alias=0,observation_ids=['id0','id1'],points=2)
    d=dict(node=dict(seed=dict(rows=rows),aliases=[0,1,0]),entries=[entry],
        scan=SimpleNamespace(norads=np.array([100,101,102,103])),all_means=np.array([0.,.1,.2,.3]))
    before=copy.deepcopy(d['node']);original_entry=copy.deepcopy(entry)
    family=dict(original_index=1,members=[dict(component='active'),dict(component='linear')])
    offer=dict(candidate_index=3,aliases=[-1,1])
    node,entries,means=configuration(d,[(family,offer)])
    assert [r['candidate_index'] for r in node['seed']['rows']]==[3,3,2]
    assert node['aliases']==[-1,1,0] and entries[0]['alias']==1
    assert entries[0]['observation_ids']==original_entry['observation_ids'] and entries[0]['points']==2
    assert d['node']==before and d['entries'][0]==original_entry
    np.testing.assert_array_equal(means,[.2,.3])


def test_predictive_only_phase_is_not_treated_as_an_entirely_unused_prior():
    p=SimpleNamespace(labels=[1,2,3],rows=[dict(candidate_index=1),dict(candidate_index=2),dict(candidate_index=3)],
        slices=[slice(0,1),slice(1,2),slice(2,3)],keep=np.array([True,False,False]))
    assert unused_count(p,[])==2
    assert unused_count(p,[dict(candidate_index=2)])==1


def test_mutual_exchange_is_atomic_and_preserves_both_families_and_predictive_points():
    rows=[dict(component='a',candidate_index=1,candidate_norad=101),dict(component='b',candidate_index=2,candidate_norad=102),
          dict(component='inactive_a',candidate_index=1,candidate_norad=101)]
    entries=[dict(component='linear_a',candidate_index=1,norad=101,alias=0,observation_ids=['x','y'],points=2),
             dict(component='linear_b',candidate_index=2,norad=102,alias=1,observation_ids=['z'],points=1)]
    d=dict(node=dict(seed=dict(rows=rows),aliases=[0,1,0]),entries=entries,scan=SimpleNamespace(norads=np.array([100,101,102])),all_means=np.array([0.,.1,.2]))
    before=copy.deepcopy((d['node'],d['entries']))
    offers=[(dict(original_index=1,members=[dict(component='a'),dict(component='linear_a')]),dict(candidate_index=2,aliases=[-1,2])),
            (dict(original_index=2,members=[dict(component='b'),dict(component='linear_b')]),dict(candidate_index=1,aliases=[1,-2]))]
    node,predictive,means=configuration(d,offers)
    assert [r['candidate_index'] for r in node['seed']['rows']]==[2,1,2]
    assert node['aliases']==[-1,1,0]
    assert [e['candidate_index'] for e in predictive]==[2,1]
    assert [e['alias'] for e in predictive]==[2,-2]
    assert [e['observation_ids'] for e in predictive]==[['x','y'],['z']]
    assert (d['node'],d['entries'])==before
    np.testing.assert_array_equal(means,[.1,.2])
    with pytest.raises(ValueError,match='only once'):configuration(d,[offers[0],offers[0]])
