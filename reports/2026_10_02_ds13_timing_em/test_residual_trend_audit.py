import numpy as np
import pytest

from residual_trend_audit import channel_design, polynomial, profile_minimum, regress, time_folds, timing_fit


def test_channel_offsets_do_not_create_a_within_channel_slope():
    times=np.arange(100,dtype=float)
    channels=np.where(times<45,1,2)
    values=np.where(channels==1,-100.,100.)
    pooled,_,_=regress(polynomial(times),values)
    controlled,_,rank=regress(channel_design(times,channels,1),values)
    assert pooled[1]/30>2
    assert rank==3
    assert controlled[-1]/30==pytest.approx(0,abs=1e-12)


def test_temporal_cv_has_complete_test_coverage_and_purges_neighbors():
    times=np.linspace(0,90,181)
    folds=time_folds(times)
    assert np.all(np.sum([test for _,test in folds],axis=0)==1)
    for train,test in folds:
        assert not np.any(train & test)
        assert np.min(np.abs(times[train,None]-times[None,test]))>1


def test_profile_search_recovers_noncentral_minimum():
    assert profile_minimum(lambda x:(x+.37)**2)==pytest.approx(-.37,abs=1e-7)
    assert profile_minimum(lambda x:(x-2)**2)==1.0


def test_timing_bias_separates_orbit_shift_from_frequency_offset():
    class Orbit:
        parameters=np.zeros(7)
        def __init__(self):self.times=np.linspace(-1,1,50)
        def change(self,delta):return 200*((self.times+delta)**2-self.times**2)
    orbit=Orbit()
    values=orbit.change(.13)-32
    result,prediction=timing_fit(orbit,values,np.ones(len(values)))
    assert result['extra_timing_s']==pytest.approx(.13,abs=1e-7)
    assert result['bias_hz']==pytest.approx(-32,abs=1e-5)
    np.testing.assert_allclose(prediction,values,atol=1e-5)
