from types import SimpleNamespace
import numpy as np
import pytest
from ds23_frequency_events import event_design
from annotate_predictive_only import prediction_design
from probe_independent_receiver_ramps import exclude_family,receiver_ramps


def test_ramp_scale_receiver_support_and_legacy_step():
    times=np.array([5.,10.,15.,20.,25.])
    event=dict(kind='receiver_RF',receiver=1,time_s=10.,sigma_hz=50.,transition_s=10.)
    got=event_design(times,[1,1,1,1,2],1,23e9,0,[event])[:,0]
    np.testing.assert_array_equal(got,[0,0,50,100,0])
    legacy=dict(event);legacy.pop('transition_s')
    np.testing.assert_array_equal(event_design(times,1,1,11.5e9,0,[legacy])[:,0],[0,50,50,50,50])
    with pytest.raises(ValueError,match='transition'):
        event_design(times,1,1,11.5e9,0,[dict(event,transition_s=-1)])


def test_predictive_event_mean_and_cross_covariance_preserved():
    track=dict(times=np.array([0.,5.,10.]),receiver=1,channel=6,rf_hz=11.5e9)
    base=np.ones((3,1));event=dict(kind='receiver',receiver=1,time_s=0.,sigma_hz=2.,transition_s=10.)
    p=SimpleNamespace(events=[event],event_start=2)
    h=prediction_design(p,track,7,base,3)
    np.testing.assert_array_equal(h,[[1,0,0],[1,0,1],[1,0,2]])
    np.testing.assert_array_equal(base,np.ones((3,1)))
    np.testing.assert_array_equal(h@np.array([3,0,4]),[3,7,11])
    cov=np.array([[2.,0,1],[0,3,0],[1,0,4]])
    assert (h@cov@h.T)[2,2]==22
    np.testing.assert_array_equal(prediction_design(SimpleNamespace(events=[]),track,7,base,1),base)
    with pytest.raises(ValueError,match='width'):
        prediction_design(p,track,7,base,4)


def test_entire_target_family_exclusion_and_timestamp_only_grid():
    rows=[dict(candidate_norad=j) for j in (10,20,10,30)]
    slices=[slice(i*2,i*2+2) for i in range(4)];original=np.ones(8,bool)
    keep=exclude_family(rows,slices,original,10,1)
    np.testing.assert_array_equal(keep,[False]*6+[True]*2)
    assert original.all()
    ramps=receiver_ramps(2,25.,'receiver')
    assert [r['time_s'] for r in ramps]==[0.,10.,20.]
    assert all(r['receiver']==2 and r['sigma_hz']==50 for r in ramps)
