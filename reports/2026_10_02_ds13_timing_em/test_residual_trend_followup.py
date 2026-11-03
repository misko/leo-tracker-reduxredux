import numpy as np
from residual_trend_followup import matched_receiver_rows, partial_correlation


def test_receiver_matching_requires_same_channel_and_no_reused_rows():
    times=np.array([0.,.1,.2,.21,0.05])
    channels=np.array([1,1,1,1,2])
    pairs=matched_receiver_rows(times,channels,np.array([0,1]),np.array([2,3,4]))
    assert len(pairs)==2
    assert len(set(p[0] for p in pairs))==2
    assert len(set(p[1] for p in pairs))==2
    assert all(channels[a]==channels[b] for a,b,_ in pairs)


def test_partial_correlation_removes_common_time_trend():
    x=np.arange(100,dtype=float)
    design=np.c_[np.ones(len(x)),x]
    assert partial_correlation(3*x+1,2*x-5,design) is None
