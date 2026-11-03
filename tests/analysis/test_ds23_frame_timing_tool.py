import numpy as np
from probe_ds23_frame_timing import clock_segments,arrival_time


def test_frame_unwrap_removes_only_affine_clock_and_preserves_known_curvature():
    t=np.linspace(0,60,101);rho=900+.04*t*t
    arrival=t+rho/299792.458+30e-6+2e-6*t
    result=clock_segments(t,arrival,rho)
    assert len(result)==1 and result[0]['RMS_us']<1e-6
    assert abs(result[0]['clock_rate_ppm']-2)<1e-8
    altered=clock_segments(t,arrival+(.01e-6*(t-30)**2),rho)
    assert altered[0]['RMS_us']>2


def test_long_counter_gaps_split_timing_without_changing_observation_time():
    t=np.r_[np.arange(5.),30+np.arange(5.)];r=clock_segments(t,t+10e-6,np.ones(10)*900)
    assert len(r)==2 and r[1]['start_index']==5 and r[1]['time_s'][0]==30


def test_epoch_arrival_keeps_probe_offset_and_avoids_large_counter_cancellation():
    source=dict(sample_rate_hz=2500000,timing=dict(session_start_device_sample_counter=10**13))
    point=dict(visit_start_counter=10**13+2500000,probe_start_ms=120,
        peak=dict(integer_epoch_sample=100,fractional_epoch_offset_samples=.25))
    actual=arrival_time(point,source,dict())
    assert abs(actual-(1.1200401))<1e-12
