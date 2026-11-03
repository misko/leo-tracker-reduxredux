from pathlib import Path
import sys
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'tools'))
from ds23_fractional_frame_jitter import FractionalFrameJitterWorkspace
from decoupled_pilot_clocks import ContinuousCoupledWorkspace


def test_zero_jitter_matches_existing_fractional_template_score_and_jacobian():
    rng = np.random.default_rng(1917)
    y = rng.normal(size=18000)+1j*rng.normal(size=18000)
    p = FractionalFrameJitterWorkspace(y, 2500000, 'upper', 141.2)
    control = ContinuousCoupledWorkspace(y, 2500000, 'upper', 141.2)
    parameters = [16432., .17, 7.3]
    old, new = control.statistics(parameters), p.statistics(parameters)
    assert new['score'] == pytest.approx(old['score'], abs=1e-13)
    np.testing.assert_allclose(new['normal'], old['normal'], atol=2e-9, rtol=2e-8)
    np.testing.assert_allclose(new['rhs'], old['rhs'], atol=2e-9, rtol=2e-8)


def test_fractional_frame_jitter_derivatives_match_finite_differences():
    rng = np.random.default_rng(1818)
    p = FractionalFrameJitterWorkspace(rng.normal(size=18000)+1j*rng.normal(size=18000), 2500000, 'lower', 141.2)
    x = np.r_[16432., .173, 7.3, np.linspace(-.015, .017, len(p.frames))]
    score = p.jitter_statistics(x, .15)
    scale = np.r_[100., 1., 20., np.full(len(p.frames), .1)]
    for k in [0, 1, 2, 3, len(x)-1]:
        delta = np.zeros(len(x)); delta[k] = scale[k]*1e-7
        derivative = (p.jitter_statistics(x+delta, .15)['cost']-p.jitter_statistics(x-delta, .15)['cost'])/2e-7
        assert derivative == pytest.approx(-2*score['rhs'][k], abs=2e-4, rel=5e-4)
