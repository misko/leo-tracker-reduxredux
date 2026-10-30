import pytest
from run_reconciled_predictive_inclusions import require_distinct_annotation
from run_reconciled_predictive_inclusions import pending_subset


def test_remaining_manifest_cannot_change_or_duplicate_candidates():
    a=dict(track_id='a',points=40);b=dict(track_id='b',points=35)
    assert pending_subset([a,b],[b])==[b]
    for changed in ([dict(b,points=50)],[b,b],[dict(track_id='c',points=35)]):
        with pytest.raises(ValueError):pending_subset([a,b],changed)


def test_different_seeds_with_same_holdout_do_not_qualify():
    result=dict(folds=[dict(seed=s) for s in [1,2,3]])
    selected=[dict(seed=s,target_held_blocks=b) for s,b in [(1,[1]),(2,[2]),(3,[1])]]
    protocol=dict(partition_plan=dict(schedule=dict(ready=True,selected=selected)))
    with pytest.raises(ValueError,match='distinct'):require_distinct_annotation(result,protocol)
    selected[2]['target_held_blocks']=[3]
    require_distinct_annotation(result,protocol)
    result['folds'][2]['seed']=4
    with pytest.raises(ValueError,match='distinct'):require_distinct_annotation(result,protocol)
