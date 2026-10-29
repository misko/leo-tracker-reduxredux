import numpy as np
from leo.analysis.research.shared_receiver_events import step_candidates


def curve(family,channel,amplitude=300.):
    t=np.arange(0.,100.);rng=np.random.default_rng(channel)
    return dict(component=str(channel),receiver=1,channel=channel,norad=family,rf_hz=11.5e9,times_s=t,
        residual_hz=50+2*t+amplitude*(t>=50)+rng.normal(0,20,len(t)),sigma_hz=40.)


def test_shared_step_requires_two_families_not_two_channels():
    one=step_candidates([curve(10,1),curve(10,2)],np.arange(20,81,2))
    assert one[0]['time_s']==50 and not any(r['candidate'] for r in one)
    two=step_candidates([curve(10,1),curve(20,2)],np.arange(20,81,2))
    assert two[0]['time_s']==50 and two[0]['candidate']
    assert abs(two[0]['amplitude_hz']-300)<20


def test_affine_trends_and_opposing_family_steps_do_not_corroborate():
    flat=step_candidates([curve(10,1,0),curve(20,2,0)],np.arange(20,81,2))
    assert not any(r['candidate'] for r in flat)
    opposite=step_candidates([curve(10,1,300),curve(20,2,-300)],np.arange(20,81,2))
    assert not any(r['candidate'] for r in opposite)
