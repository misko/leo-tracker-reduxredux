import numpy as np
from leo.analysis.research.grouped_prediction import geometry_partition_schedule,replay_split


def test_schedule_keeps_whole_blocks_guards_and_unique_target_evidence():
    times=np.arange(0.,120.,.5);focus=times[(times>=20)&(times<80)]
    seeds=[20261029,94721,4081,*np.random.default_rng(20261029).integers(0,2**31-1,64)]
    r=geometry_partition_schedule(times,focus,seeds=seeds)
    assert r['ready'] and len(r['selected'])==3
    assert len({tuple(s['target_held_blocks']) for s in r['selected']})==3
    for receipt in r['selected']:
        train,held=replay_split(focus,receipt)
        assert train.sum()>=8 and held.sum()>=4 and not np.any(train&held)
        assert receipt['block_s']==12 and receipt['guard_s']==2
    assert geometry_partition_schedule(times,focus,seeds=seeds)==r


def test_background_does_not_manufacture_distinct_target_groups():
    times=np.arange(0.,300.,.5)
    r=geometry_partition_schedule(times,np.arange(1.,21.,.5),seeds=range(100))
    assert not r['ready'] and r['reason']=='fewer_than_three_target_blocks'
    r=geometry_partition_schedule(times,np.arange(1.,60.,.5),seeds=[4,4,4])
    assert not r['ready'] and len(r['selected'])==1
