import pytest
from report import REFERENCE, error_km, statistics, temporal_sensitivity


def test_position_distance_and_failure_denominator():
    assert error_km(REFERENCE)==pytest.approx(0)
    assert error_km((REFERENCE[0]+1,REFERENCE[1]))==pytest.approx(111.1949266)
    r=statistics([dict(error_km=1.,curved_RMS_hz=100),dict(error_km=None)],2)
    assert r['localized']==1 and r['unavailable']==1 and r['mean_km']==1.


def test_time_blocks_exclude_unshared_times_and_weight_blocks_equally():
    step=3*3600*10**9
    rows=[dict(mode='adaptive',error_km=e,captured_utc_ns=t) for e,t in [(10.,0),(2.,step),(4.,2*step)]]
    rows += [dict(mode='fast',error_km=1.,captured_utc_ns=t) for t in [step,step,2*step]]
    d=temporal_sensitivity(rows)
    assert d['shared_blocks']==2
    assert d['adaptive_minus_fast_km']==2.
