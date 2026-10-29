import numpy as np

from inventory_cohort_unassociated import remaining_track


def test_partial_track_counts_and_span_use_only_unassociated_points():
    t=np.arange(40.)
    track=dict(key='test',receiver=2,channel=3,observation_ids=list(range(40)),
               times=t,values=10*t*t,residual_rms_hz=12.,pieces=[{}],quality_status='no_structure_detected')
    result=remaining_track(track,set(range(10)))
    assert result['unassociated_points']==30
    assert result['total_track_points']==40
    assert result['start_s']==10
    assert result['end_s']==39
    assert result['span_s']==29
    assert result['big'] and result['active_curvature']
    assert not result['wholly_unassociated']
    assert remaining_track(track,set(range(40))) is None


def test_long_linear_track_is_big_but_not_curved_and_gap_is_visible():
    t=np.r_[np.arange(10.),np.arange(30.,40.)]
    track=dict(key='test',receiver=1,channel=8,observation_ids=list(range(20)),
               times=t,values=1200*t+500,residual_rms_hz=0.,pieces=[{}],quality_status='no_structure_detected')
    result=remaining_track(track,set())
    assert result['big'] and result['wholly_unassociated']
    assert not result['active_curvature']
    assert result['largest_gap_s']==21
