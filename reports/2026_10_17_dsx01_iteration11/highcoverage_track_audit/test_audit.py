"""Synthetic checks for descriptive curve summaries, no source or orbit calls."""

import numpy as np
from numpy.testing import assert_allclose

from audit import ALIAS_HZ, curve_summary, describe, local_unwrap


def test_local_alias_seam_and_whole_period_invariance():
    y=np.array([110000.,113000.,-111000.,-108000.])
    unwrapped=local_unwrap(y)
    assert np.ptp(unwrapped)<10000
    shifted=local_unwrap(y+ALIAS_HZ)
    assert_allclose(shifted-unwrapped,ALIAS_HZ,atol=1e-9)


def test_fixed_quadratic_and_leave_one_out_predict_exact_curve():
    t=np.linspace(0,20,9);y=400+50*t-3*t*t
    summary=curve_summary(t,y)
    assert summary['degree']==2
    assert summary['leave_one_out_rms_hz']<1e-10
    assert_allclose(summary['curvature_hz_s2'],-6,atol=1e-10)
    assert_allclose(summary['slope_at_center_hz_s'],-10,atol=1e-10)


def test_short_curves_and_association_annotation_keep_all_members():
    assert curve_summary([0,1],[3,4])['degree'] is None
    assert curve_summary([0,1,2],[3,4,5])['degree']==1
    rows=[dict(observation_id=str(i),time_s=float(i),measured_cfo_hz=100+i*10) for i in range(7)]
    result=describe(rows,{str(i):i%2==0 for i in range(7)})
    assert result['points']==7 and result['unassociated']==3
    assert result['all_members_curve']['degree']==2
    assert result['unassociated_members_curve']['degree']==1
    assert len(result['observations'])==7
