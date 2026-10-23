import numpy as np
from types import SimpleNamespace
from probe_ds23_iteration014_augmented_family import choose_group,relabel


def test_augmented_group_must_be_failed_multi_source_and_already_active():
    def trial(labels,points,valid=False):return dict(paired_valid=valid,added_curved_points=points,additions=[dict(candidate_index=j,component=str(k)) for k,j in enumerate(labels)])
    expected=trial([1,1],60)
    assert choose_group([trial([1],100),trial([2,2],200),trial([1,3],90),trial([1,1],80,True),expected],{1}) is expected


def test_complete_family_relabel_is_atomic_and_preserves_other_labels_and_input():
    d=dict(entries=[dict(component='linear',candidate_index=1,norad=10,alias=0)],scan=SimpleNamespace(norads=[0,10,20]),all_means=np.array([0.,1.,2.]))
    proposal=dict(node=dict(seed=dict(rows=[dict(component='a',candidate_index=1,candidate_norad=10),dict(component='b',candidate_index=2,candidate_norad=20)]),aliases=[0,1]))
    node,entries,means=relabel(d,proposal,1,2,{'a':-1,'linear':1})
    assert node['seed']['rows'][0]['candidate_index']==2 and node['aliases']==[-1,1]
    assert entries[0]['candidate_index']==2 and entries[0]['alias']==1 and means.tolist()==[2.]
    assert proposal['node']['seed']['rows'][0]['candidate_index']==1 and d['entries'][0]['alias']==0
