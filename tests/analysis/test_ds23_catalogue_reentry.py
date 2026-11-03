from types import SimpleNamespace
import numpy as np

from ds23_catalogue_reentry import complete_groups,selected_indices
from ds23_owner_reentry import strongest_per_owner


def test_identity_search_keeps_incumbent_and_is_stable():
    assert selected_indices([5,1,1,np.inf],0,2)==[0,1,2]


def test_new_groups_rank_by_available_evidence_not_identity_replacement_gain():
    tracks=[dict(times=np.arange(n),receiver=1,channel=ch,observation_ids=[f'{k}-{i}' for i in range(n)])
        for k,(n,ch) in enumerate([(20,1),(30,2),(12,3),(12,4)])]
    p=SimpleNamespace(scan=SimpleNamespace(tracks=tracks),rows=[dict(candidate_index=j) for j in [9,9,3,3]],
        members=list(range(4)),slices=[slice(0,20),slice(20,50),slice(50,62),slice(62,74)],keep=np.zeros(74,bool))
    groups=complete_groups(p,set())
    assert [(r['original_index'],r['added_points']) for r in groups]==[(9,50),(3,24)]
    p.keep[0]=True
    assert [r['original_index'] for r in complete_groups(p,set())]==[3]


def test_owner_selection_keeps_complete_longer_curve_without_trimming_points():
    tracks=[dict(times=np.arange(n),receiver=1,channel=ch,key=str(k)) for k,(n,ch) in enumerate([(16,1),(44,1),(82,7)])]
    p=SimpleNamespace(scan=SimpleNamespace(tracks=tracks),members=[0,1,2])
    g=strongest_per_owner(dict(rows=[0,1,2],original_index=5),p)
    assert g['rows']==[1,2]
    assert g['added_points']==126
