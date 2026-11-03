from types import SimpleNamespace
import numpy as np
import pytest
import ds23_bracketed_clock as clock


def test_common_clock_bound_comes_from_original_host_interval():
    doc=dict(timing=dict(qualified=True,first_sample_earliest_utc_ns=1000000000,
                         first_sample_latest_utc_ns=1360000000))
    r=clock.clock_interval(doc,1180000000)
    assert r['lower_s']==-.18 and r['upper_s']==.18
    with pytest.raises(ValueError):clock.clock_interval(doc,1500000000)


def test_fast_bracket_accounts_for_realtime_monotonic_offsets():
    doc=dict(source={},clock_anchor=dict(before=dict(realtime_ns=1000,monotonic_ns=100),
                                         after=dict(realtime_ns=1200,monotonic_ns=299)))
    r=clock.clock_interval(doc,1100)
    assert r['lower_s']==pytest.approx(-100e-9)
    assert r['upper_s']==pytest.approx(100e-9)


def test_time_shift_not_removed_as_an_independent_TLE_phase(monkeypatch):
    p=SimpleNamespace(reference=np.array([.2,-.1]))
    def geometry(view,position,alt):
        derivative=np.array([100.,200.])
        frequency=1000+derivative*view.reference
        return dict(intercept=frequency-derivative*view.reference,derivative=derivative)
    monkeypatch.setattr(clock,'geometry_features',geometry)
    g=clock.clock_geometry(p,[0.,0.],.05)
    np.testing.assert_allclose(g['intercept'],[1005.,1010.])
    np.testing.assert_array_equal(p.reference,[.2,-.1])


def test_linear_predictions_cannot_estimate_UTC():
    with pytest.raises(ValueError,match='cannot estimate'):
        clock.attach_clock_prediction(SimpleNamespace(fixed_shift_s=None),[{}],[])


def test_bound_repair_accepts_only_roundoff():
    from run_ds23_bracketed_clock_v2 import bounded_shift
    interval=dict(lower_s=-.18,upper_s=.18)
    assert bounded_shift(.18+1e-16,interval)==.18
    assert bounded_shift(-.18-1e-16,interval)==-.18
    assert bounded_shift(.05,interval)==.05
    with pytest.raises(ValueError):bounded_shift(.1801,interval)


def test_recovery_wrapper_uses_declared_interval_argument(monkeypatch):
    import run_ds23_bracketed_clock_v2 as recovery
    monkeypatch.setattr(recovery,'original_factory',lambda *args,**kwargs:kwargs['fixed_shift_s'])
    args=[None]*8+[dict(lower_s=-.18,upper_s=.18)]
    assert recovery.clock_problem(*args,fixed_shift_s=.18+1e-16)==.18
