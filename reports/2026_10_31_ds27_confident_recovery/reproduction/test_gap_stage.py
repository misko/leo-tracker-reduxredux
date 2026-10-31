import numpy as np
import pytest
from gap_stage import partitions

def test_exact_five_second_gap_does_not_split():
    t=np.r_[np.arange(12),np.arange(16,28)]
    assert partitions(t)==[(0,24)]

def test_all_eligible_components_and_short_remainder():
    t=np.r_[np.arange(20),np.arange(26,43),np.arange(50,56)]
    assert partitions(t)==[(0,20),(20,37)]

@pytest.mark.parametrize('times',[[0,0],[2,1],[0,float('nan')],[]])
def test_bad_times_fail_closed(times):
    with pytest.raises(ValueError):partitions(times)
