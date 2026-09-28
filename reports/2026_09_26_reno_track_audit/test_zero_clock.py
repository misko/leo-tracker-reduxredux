import numpy as np
import pytest
from evaluate_zero_clock import best_row,TrackPrediction,profile_track,score_profiled_location


def test_identity_selection_ignores_evaluation_and_handles_missing():
    a=dict(candidate_id='2',training_rms_hz=1,reserved_rms_hz=900)
    b=dict(candidate_id='1',training_rms_hz=2,reserved_rms_hz=0)
    assert best_row(a,b)==a
    assert best_row(None,a)==a
    assert best_row(a,None)==a
    assert best_row(a,dict(a,candidate_id='1'))['candidate_id']=='1'


def test_zero_clock_still_fits_constant_offset():
    track=TrackPrediction('t',4,('1',),np.array([0.]),np.array([10.,11.,12.,13.]),
                          np.array([[[0.,1.,2.,3.]]]),np.array([1,1,0,0],bool),np.array([True]))
    rows=profile_track(track)
    fit=score_profiled_location([('s',[(4,np.array([0.]),rows)])],0,hard_shared=True)
    assert fit['scans'][0]['clock_tau_s']==0
    assert rows[0]['cfo_hz']==pytest.approx(10)
    assert fit['reserved_capped_weighted_rms_hz']==pytest.approx(0)
