import numpy as np
import pytest
from nuisance_core import fit_profiles,select_fit


def test_offset_is_distinct_from_linear_drift_and_training_only():
    t=np.arange(8.)
    train=np.array([1,1,1,1,0,0,0,0],bool)
    measured=100+3*t
    profile,residual=fit_profiles(t,measured,np.zeros((1,8)),train,[0])
    fit=select_fit(profile,residual,t,train,5)
    assert fit['offset_hz']==104.5
    assert fit['residual_slope_hz_per_s']==pytest.approx(3)
    assert fit['linear_drift_score_rms_hz']==pytest.approx(0)
    measured[~train]+=70
    p2,r2=fit_profiles(t,measured,np.zeros((1,8)),train,[0])
    f2=select_fit(p2,r2,t,train,5)
    assert f2['residual_slope_hz_per_s']==fit['residual_slope_hz_per_s']
    assert f2['offset_hz']==fit['offset_hz']
    assert f2['linear_drift_score_rms_hz']==pytest.approx(70)


def test_expanded_grid_can_expose_clipped_minimum():
    t=np.arange(8.)
    train=np.arange(8)%2==0
    taus=np.arange(-30,31)
    prediction=(taus[:,None]+12)*t
    p,r=fit_profiles(t,np.zeros(8),prediction,train,taus)
    narrow=select_fit(p,r,t,train,5)
    wide=select_fit(p,r,t,train,30)
    assert narrow['tau_s']==-5 and narrow['boundary']
    assert wide['tau_s']==-12 and not wide['boundary']
    assert wide['score_rms_hz']==0


def test_missing_partition_is_rejected():
    with pytest.raises(ValueError,match='partitions'):
        fit_profiles(np.arange(3),np.zeros(3),np.zeros((1,3)),[1,1,1],[0])
