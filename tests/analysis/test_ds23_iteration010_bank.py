import copy

import pytest

from repair_ds23_iteration010_bank import filtered_bank


def node(candidate):
    return dict(seed=dict(rows=[dict(component='x',candidate_index=candidate,candidate_norad=100+candidate)],state={'stale':True}),aliases=[0])


def test_rescued_bank_keeps_current_and_real_discoveries_deduplicated_and_cold():
    original=node(1);other=node(2);before=copy.deepcopy(original)
    rows,excluded,count=filtered_bank([original,other,copy.deepcopy(other)],set(),dict(cold=True))
    assert len(rows)==2 and not excluded and count==2
    assert rows[0]['seed']['rows']==original['seed']['rows']
    assert all(r['seed']['state']==dict(cold=True) for r in rows)
    assert original==before


def test_bank_cannot_remove_predictive_families_or_change_measurement_order():
    rows,excluded,count=filtered_bank([node(1),node(2)],{1},{})
    assert len(rows)==1 and len(excluded)==1 and count==2
    bad=node(2);bad['seed']['rows'][0]['component']='wrong'
    with pytest.raises(ValueError,match='observation order'):filtered_bank([node(1),bad],set(),{})
