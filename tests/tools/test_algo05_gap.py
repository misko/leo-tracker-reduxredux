import json
import pytest
from algo05_gap_stage import partitions
from algo05_recovery_worker import select

def test_timing_only_fragments_keep_whole_groups():
    assert partitions(list(range(14))+list(range(30,46)))==[(0,14),(14,30)]
    assert partitions([0,1,2])==[]
    with pytest.raises(ValueError):partitions([0,0,1])

def test_rf_selection_never_uses_location_or_unions_trials():
    def row(margin,count):return dict(identity={'minimum_margin':margin},track_id='a',
        qualification=dict(qualified=True,added_points={'fitted_c':count}),position='invalid')
    a=row(30,12);b=row(20,40)
    assert select([b,a]) is a
    a['qualification']['qualified']=False
    assert select([a,b]) is b
