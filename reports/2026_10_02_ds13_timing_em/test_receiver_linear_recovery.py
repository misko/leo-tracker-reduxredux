import numpy as np
from receiver_linear_recovery import design, solve, blocked_folds


def test_shared_slope_with_distinct_track_offsets():
    t=np.tile(np.linspace(0,300,31),2);ids=np.repeat([1,2],31)
    y=np.where(ids==1,100.,-200.)+3.5*(t-150)
    a=design(t,ids,'track_offsets_shared_line')
    for balanced in (False,True):
        co,pred=solve(a,y,ids,balanced=balanced)
        np.testing.assert_allclose(pred,y,atol=1e-10)
        assert abs(co[-1]/100-3.5)<1e-10


def test_opposite_slopes_cannot_be_removed_by_common_slope():
    t=np.tile(np.linspace(0,300,31),2);ids=np.repeat([1,2],31)
    y=np.where(ids==1,2.,-2.)*(t-150)
    co,pred=solve(design(t,ids,'track_offsets_shared_line'),y,ids)
    assert abs(co[-1])<1e-10
    assert np.sqrt(np.mean((y-pred)**2))>100


def test_temporal_folds_exclude_adjacent_same_track_rows():
    t=np.tile(np.linspace(0,100,101),2);ids=np.repeat([1,2],101)
    coverage=np.zeros(len(t),int)
    for train,test in blocked_folds(t,ids):
        coverage+=test
        assert not np.any(train&test)
        for s in (1,2):
            assert np.min(np.abs(t[train&(ids==s),None]-t[None,test&(ids==s)]))>1
    np.testing.assert_array_equal(coverage,np.ones(len(t)))
