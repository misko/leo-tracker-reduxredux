import numpy as np
from evaluate import corrections,score


def test_donor_scan_balance_and_two_scan_minimum():
    rows=[dict(norad=1,session_id='a',training_slope_hz_s=1.)]*10
    rows += [dict(norad=1,session_id='b',training_slope_hz_s=3.),dict(norad=2,session_id='c',training_slope_hz_s=8.)]
    assert corrections(rows)=={1:dict(slope=2.,donor_scans=2)}


def test_fixed_slope_removes_synthetic_drift_without_held_leakage():
    t=np.arange(60.)-29.5;mask=np.arange(60)%2==0
    r=dict(residual_hz=(10000+8*t).tolist(),centered_times_s=t.tolist(),training_mask=mask.tolist())
    base=score(r,0);fixed=score(r,8)
    assert fixed[0]>base[0] and fixed[1]>base[1]
    r['residual_hz']=(np.array(r['residual_hz'])+np.where(mask,0,1e5)).tolist()
    assert score(r,8)[0]==fixed[0]
