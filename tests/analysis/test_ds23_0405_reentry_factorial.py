import copy
from types import SimpleNamespace

import numpy as np
import pytest

import probe_ds23_0405_reentry_factorial as factorial


@pytest.mark.parametrize('basis',['original','fine'])
@pytest.mark.parametrize('curves,expected',[('none',0),('owner',7),('all',9)])
def test_factorial_preserves_incumbent_and_changes_only_declared_inactive_rows(monkeypatch,basis,curves,expected):
    tracks=[dict(key='short',receiver=1,channel=1,times=np.arange(2.)),
        dict(key='long',receiver=1,channel=1,times=np.arange(3.)),
        dict(key='other_band',receiver=1,channel=7,times=np.arange(4.)),
        dict(key='incumbent',receiver=2,channel=2,times=np.arange(2.))]
    scan=SimpleNamespace(tracks=tracks,rx_basis=[np.ones((len(t['times']),1)) for t in tracks])
    rows=[dict(component=t['key'],candidate_index=0 if k<3 else 1,candidate_norad=100 if k<3 else 101) for k,t in enumerate(tracks)]
    node=dict(seed=dict(rows=rows,state=dict(smooth=[[0.],[0.]])),aliases=[0,0,0,1])
    mask=np.array([False]*9+[True]*2);slices=[slice(0,2),slice(2,5),slice(5,9),slice(9,11)]
    entry=dict(component='predictive',candidate_index=1,observation_ids=['p0','p1'])
    data=dict(scan=scan,node=node,keep=mask,base=SimpleNamespace(scan=scan,members=list(range(4)),slices=slices),
        entries=[entry],all_means=np.array([.1,.2,.3]))
    original_node=copy.deepcopy(node)
    monkeypatch.setattr(factorial,'setup',lambda case:data)
    def fine(value):
        changed=copy.copy(value);changed.rx_basis=[np.ones((len(t['times']),2)) for t in tracks];return changed
    monkeypatch.setattr(factorial,'fine_view',fine)
    protocol=dict(group=dict(original_index=0,rows=[0,1,2],owners=2,added_points=9))
    task=dict(basis=basis,curves=curves,offer=dict(candidate_index=2,norad=102,aliases=[-1,0,1]))
    result,old,selected=factorial.context(task,protocol)
    np.testing.assert_array_equal(old,mask)
    assert int(result['keep'].sum()-old.sum())==expected and np.all(result['keep'][old])
    assert result['node']['seed']['rows'][3]==node['seed']['rows'][3]
    assert result['node']['aliases'][3]==1 and result['entries']==[entry]
    for k in range(3):
        assert result['node']['seed']['rows'][k]['candidate_index']==(2 if k in selected else 0)
        assert result['node']['aliases'][k]==(task['offer']['aliases'][k] if k in selected else 0)
    if curves=='owner':assert selected==[1,2]
    assert node==original_node
    assert np.asarray(result['node']['seed']['state']['smooth']).shape==(2,2 if basis=='fine' else 1)
