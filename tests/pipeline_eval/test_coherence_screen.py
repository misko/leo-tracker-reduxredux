import numpy as np

from tools.pipeline_eval.variants.experimental.coherence_screen import coherence, result


def test_repetition_ignores_frame_phase_and_does_not_borrow_other_lane():
    rng = np.random.default_rng(104)
    samples = rng.integers(-200,201,(200000,2,2),dtype=np.int16)
    shape = samples[:40000,0,:].astype(int)
    for frame in range(5):
        samples[frame*40000:(frame+1)*40000,0,:] = (-1)**frame * shape
    assert coherence(samples,0) > .999
    assert coherence(samples,1) < .01
    samples[:,1,:] = 0
    assert coherence(samples,1) is None


def test_screen_cost_includes_screening_the_retained_lanes():
    rows = [dict(score=.01,factors=0,native_ns=40,screen_ns=5),
            dict(score=.1,factors=2,native_ns=60,screen_ns=5)]
    assert result(rows,.1)["estimated_native_ratio"] == .7
    assert result(rows,.11)["lost_factors"] == 2
