from types import SimpleNamespace
import numpy as np
import pytest
from ds23_frequency_events import event_design,track_events,family_event_frequency


def test_pulse_turns_off_and_scopes_receiver_and_family_separately():
    t=np.array([9.,10.,12.,14.,15.,16.]);rx=np.array([1,1,2,1,1,1]);j=np.array([4,4,4,5,4,4])
    event=dict(time_s=10.,end_s=15.,sigma_hz=100.)
    result=event_design(t,rx,np.ones(6),np.full(6,11.5e9),j,
        [dict(event,kind='receiver',receiver=1),dict(event,kind='family',candidate_index=4)])
    np.testing.assert_array_equal(result,[[0,0],[100,100],[0,100],[100,0],[0,0],[0,0]])


def test_family_additive_hz_and_fractional_scaling_preserve_gate_units():
    t=np.array([9.,10.,14.,15.]);track=dict(times=t,receiver=1,channel=8,rf_hz=12.65e9)
    event=dict(kind='family',candidate_index=7,time_s=10.,end_s=15.,sigma_hz=100.)
    for scaled,expected in [(False,200.),(True,220.)]:
        events=[dict(event,rf_scaled=scaled)];p=SimpleNamespace(events=events,event_start=3,
            calculate=lambda _:dict(coefficient=np.array([0.,0.,0.,2.])))
        actual=track['rf_hz']/11.5e9*family_event_frequency(p,None,track,7)
        np.testing.assert_allclose(actual,[0,expected,expected,0])
        np.testing.assert_allclose(actual,track_events(track,7,events)@np.array([2.]))
        np.testing.assert_array_equal(family_event_frequency(p,None,track,8),np.zeros(4))


def test_original_step_and_ramped_pulse_semantics():
    t=np.array([9.,10.,11.,12.,15.,16.,17.,18.]);event=dict(kind='family',candidate_index=2,time_s=10.,sigma_hz=100.)
    coords=(t,np.ones(8),np.ones(8),np.full(8,11.5e9),np.full(8,2))
    np.testing.assert_array_equal(event_design(*coords,[event])[:,0],[0,100,100,100,100,100,100,100])
    np.testing.assert_array_equal(event_design(*coords,[dict(event,end_s=15.,transition_s=2.)])[:,0],[0,0,50,100,100,50,0,0])
    with pytest.raises(ValueError,match='end after start'):
        event_design(*coords,[dict(event,end_s=9.)])


def test_exact_orbit_replay_preserves_family_pulse(monkeypatch):
    import audit_explicit_phase_endpoint as audit
    t=np.arange(4.);track=dict(key='curve',times=t,rf_hz=11.5e9)
    event=dict(kind='family',candidate_index=7,time_s=1.,end_s=3.,sigma_hz=100.)
    track.update(receiver=1,channel=1)
    f=np.array([10.,210.,210.,10.]);c=dict(coefficient=np.array([2.]),conditional_residual_hz=np.zeros(4))
    p=SimpleNamespace(events=[event],event_start=0,explicit_phase_family=7,
        calculate=lambda _:c,conditional_frequency=lambda _: (f.copy(),np.ones(4)*30),
        rows=[dict(candidate_index=7)],members=[0],slices=[slice(0,4)],q=np.ones(4),
        keep=np.ones(4,bool),scan=SimpleNamespace(tracks=[track]))
    monkeypatch.setattr(audit,'family_frequency',lambda *a,**k:(np.ones(4)*10,np.ones(4)*30))
    def gates(problem,x,entries):
        np.testing.assert_array_equal(problem.calculate(x)['conditional_residual_hz'],np.zeros(4))
        np.testing.assert_array_equal(problem.conditional_frequency(x)[0],f)
        return {'unchanged':1.}
    monkeypatch.setattr(audit,'gate_slacks',gates)
    result=audit.exact_gate_replay(p,None,[])
    assert result['all_pass'] and result['maximum_linearization_difference_hz']==0
