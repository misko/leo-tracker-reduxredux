from pathlib import Path
import sys
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from local_pilot_refinement import PilotWorkspace
from sign_aware_pilot import sign_spectrum,sign_aware_fit


def scene(random_phase=False,delta=75.):
    fs=2500000.;epoch=23.2;base=dict(CFO_hz=12345.,offset_samples=.125,modulation_ppm=5.)
    p=PilotWorkspace(np.zeros(50000,complex),fs,'lower',epoch)
    r=p.replica(base['offset_samples'],base['modulation_ppm'])
    rng=np.random.default_rng(177);y=.15*(rng.normal(size=len(r))+1j*rng.normal(size=len(r)))
    f=base['CFO_hz']+delta
    for k,ix in enumerate(p.frames):
        phase=rng.uniform(-np.pi,np.pi) if random_phase else .43+np.pi*int(rng.integers(2))
        y[ix]+=r[ix]*(1+.1*rng.normal())*np.exp(1j*phase+2j*np.pi*f*(p.t[ix]-p.mid))+.3+.2j
    return PilotWorkspace(y,fs,'lower',epoch),base,f


def test_signed_frame_carrier_recovers_truth_and_predicts_heldout_frames():
    p,base,truth=scene()
    result=sign_aware_fit(p,base,seed=91)
    assert abs(result['fits']['all']['CFO_hz']-truth)<.2
    assert min(result['heldout_phase_fraction'].values())>.99
    assert result['accepted'],result['checks']


def test_exact_within_frame_likelihood_resolves_half_frame_alias():
    p,base,truth=scene(delta=225.)
    result=sign_aware_fit(p,base,seed=92)
    assert abs(result['fits']['all']['CFO_hz']-truth)<.2
    assert abs(result['fits']['even']['CFO_hz']-truth)<.3
    assert abs(result['fits']['odd']['CFO_hz']-truth)<.3
    assert result['checks']['alias_separation']


def test_arbitrary_frame_phases_do_not_get_forced_into_sign_model():
    p,base,_=scene(random_phase=True)
    result=sign_aware_fit(p,base,seed=93)
    assert not result['accepted']


def test_restricted_phase_profile_cannot_explain_more_than_free_complex_gains():
    p,base,truth=scene()
    f=[truth-30,truth,truth+30]
    constrained=sign_spectrum(p,f,base['offset_samples'],base['modulation_ppm'])['score']
    free=p.evaluate(f,base['offset_samples'],base['modulation_ppm'])
    assert np.all(constrained<=free+1e-12)
