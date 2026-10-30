import copy
import numpy as np
import pytest
from leo.analysis.research.grouped_prediction import shifted_geometry_partition_schedule,replay_split
from annotation_partition_plan import selected_seeds,planned_split,require_distinct_annotation


def test_shifted_schedule_preserves_guards_and_physical_holdouts():
    times=np.arange(0,300,.25);focus=np.linspace(78.23,105.91,28);times=np.r_[times,focus]
    seeds,plan=selected_seeds(None,'target',times,focus,[],distinct=True,shifted_origin=True)
    assert len(seeds)==3
    folds=[]
    for seed in seeds:
        train,held,receipt=planned_split(times,focus,seed,plan)
        assert receipt['block_s']==12 and receipt['guard_s']==2
        assert not np.any(train&held)
        assert np.min(abs(times[train,None]-times[None,held]))>=2
        t,h=replay_split(focus,receipt)
        assert t.sum()>=8 and h.sum()>=4
        folds.append(dict(seed=seed,split=receipt))
    require_distinct_annotation({'folds':folds},{'partition_plan':plan})
    bad=copy.deepcopy(folds);bad[0]['split']['block_origin_s']+=1
    with pytest.raises(ValueError,match='frozen schedule'):require_distinct_annotation({'folds':bad},{'partition_plan':plan})


def test_legacy_receipts_keep_zero_origin_and_equal_times_share_groups():
    receipt=dict(block_s=12,guard_s=2,held_blocks=[1])
    times=np.array([9.,10.,12.,12.,23.,25.,26.,27.])
    train,held=replay_split(times,receipt)
    np.testing.assert_array_equal(held,[0,0,1,1,1,0,0,0])
    np.testing.assert_array_equal(train,[1,0,0,0,0,0,0,1])
    shifted=dict(receipt,block_origin_s=3)
    a,b=replay_split(times+3,shifted)
    np.testing.assert_array_equal(a,train);np.testing.assert_array_equal(b,held)


def test_shifted_replay_rejects_changed_target_and_short_support():
    focus=np.linspace(78.23,105.91,28);times=np.r_[np.arange(0,300,.25),focus]
    seeds,plan=selected_seeds(None,'target',times,focus,[],distinct=True,shifted_origin=True)
    with pytest.raises(ValueError,match='timestamps changed'):
        planned_split(times,focus+.1,seeds[0],plan)
    with pytest.raises(ValueError,match='scan support changed'):
        planned_split(np.r_[times,times],focus,seeds[0],plan)
    short=np.linspace(80,86,28)
    seeds,plan=selected_seeds(None,'short',np.r_[times,short],short,[],distinct=True,shifted_origin=True)
    assert seeds==[] and plan['geometry_only_early_exit']
    assert not plan['schedule']['ready']
