from pathlib import Path
import sys
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from local_pilot_refinement import PilotWorkspace
from sign_aware_pilot import sign_aware_fit
from ds23_sign_carrier_prediction import within_frame_carrier_prediction


def scene(interframe_bias=0.):
    fs=2500000.;base=dict(CFO_hz=12345.,offset_samples=0.,modulation_ppm=0.)
    p=PilotWorkspace(np.zeros(50000,complex),fs,'lower',23.2);r=p.replica()
    rng=np.random.default_rng(718);y=.15*(rng.normal(size=len(r))+1j*rng.normal(size=len(r)))
    for ix in p.frames:
        t=p.t[ix].mean();phase=.3+np.pi*int(rng.integers(2))+2*np.pi*interframe_bias*(t-p.mid)
        y[ix]+=r[ix]*np.exp(1j*phase+2j*np.pi*base['CFO_hz']*(p.t[ix]-p.mid))
    return PilotWorkspace(y,fs,'lower',p.epoch),base


def test_actual_sign_modulated_carrier_predicts_raw_frames():
    p,base=scene();sign=sign_aware_fit(p,base)
    assert sign['accepted']
    assert within_frame_carrier_prediction(p,base,sign)['passed']


def test_regular_frame_phase_progression_is_not_automatically_carrier():
    p,base=scene(interframe_bias=70.)
    sign=sign_aware_fit(p,base)
    # The frame phase can look stable and predictive despite describing a
    # separate frame-phase process. Within-frame RF must disqualify it.
    assert abs(sign['fits']['all']['CFO_hz']-base['CFO_hz'])>50
    guard=within_frame_carrier_prediction(p,base,sign)
    assert not guard['passed']
    assert max(r['heldout_negative_twice_log_likelihood_loss'] for r in guard['folds'])>9
