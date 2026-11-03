from pathlib import Path
import sys
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'tools'))
from ds23_frame_timing_jitter import FrameJitterWorkspace, restrict_samples
from fast_local_pilot_refinement import FastPilotWorkspace


def workspace():
    rng = np.random.default_rng(414)
    return FrameJitterWorkspace(rng.normal(size=18000)+1j*rng.normal(size=18000), 2500000, 'lower', 400.2)


def test_zero_jitter_signal_and_score_reproduce_published_local_model():
    p = workspace(); base = FastPilotWorkspace(p.y, p.fs, 'lower', p.epoch)
    parameters = [1023., .12, -4.]
    signal, *_ = p.signal_and_derivatives(np.r_[parameters, np.zeros(len(p.frames))])
    np.testing.assert_allclose(signal, base.replica(.12, -4.)*np.exp(2j*np.pi*1023.*(p.t-p.mid)), atol=1e-12)
    old = base.statistics(parameters)
    new = p.jitter_statistics(np.r_[parameters, np.zeros(len(p.frames))], .15)
    assert new['score'] == pytest.approx(old['score'], abs=1e-15)


def test_projected_jitter_score_derivative_matches_finite_difference():
    p = workspace(); x = np.r_[1023., .123, -4., np.linspace(-.02, .02, len(p.frames))]
    s = p.jitter_statistics(x, .15)
    scale = np.r_[100., 1., 20., np.full(len(p.frames), .1)]
    for k in [0, 1, 2, 3, len(x)-1]:
        delta = np.zeros(len(x)); delta[k] = scale[k]*1e-7
        difference = (p.jitter_statistics(x+delta, .15)['cost']-p.jitter_statistics(x-delta, .15)['cost'])/2e-7
        assert difference == pytest.approx(-2*s['rhs'][k], abs=2e-4, rel=5e-4)


def test_training_fit_does_not_read_changed_heldout_samples():
    p = workspace(); train = restrict_samples(p, 0)
    baseline = dict(CFO_hz=1023., offset_samples=.12, modulation_ppm=-4.)
    first = train.jitter_fit(baseline, iterations=2)
    q = workspace(); heldout = restrict_samples(q, 1)
    for ix in heldout.frames:
        q.y[ix] *= 1000j
    second = restrict_samples(q, 0).jitter_fit(baseline, iterations=2)
    for key in ['CFO_hz', 'offset_samples', 'modulation_ppm', 'frame_jitter_samples']:
        np.testing.assert_array_equal(first[key], second[key])
