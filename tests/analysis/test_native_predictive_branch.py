from types import SimpleNamespace
import numpy as np
import pytest
from native_predictive_branch import append_branch
from leo.analysis.research.retained_track_likelihood import PERIOD


def test_append_preserves_original_calibration_and_native_alias_identity():
    scan=SimpleNamespace(case='scan',tracks=[],white=[],rx_basis=[],curved=[],times=np.arange(5.))
    obs=[dict(observation_id=str(i),time_s=float(i),receiver=1,channel=7,actual_rf_hz=12.4e9,measured_cfo_hz=1000.*i) for i in range(8)]
    b=dict(branch_id='b',observation_ids=[o['observation_id'] for o in obs],times_s=[o['time_s'] for o in obs],
        values_hz=[o['measured_cfo_hz']+PERIOD for o in obs],alias_lifts=[1]*8,receiver=1,channel=7,rf_hz=12.4e9,
        quality_status='insufficient_support',pieces=[],RMS_hz=10.)
    changed,index=append_branch(scan,b,obs,set())
    assert index==0 and changed.curved==[] and changed.times is scan.times and not scan.tracks
    np.testing.assert_allclose(changed.tracks[0]['values'],b['values_hz'])
    with pytest.raises(ValueError,match='overlap'):append_branch(scan,b,obs,{'0'})
    with pytest.raises(ValueError,match='measured CFO'):append_branch(scan,dict(b,values_hz=np.array(b['values_hz'])+1),obs,set())
    with pytest.raises(ValueError,match='lanes'):append_branch(scan,dict(b,rf_hz=12e9),obs,set())
