from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'tools'))
from probe_ds23_differential_epoch import PERIOD, epoch_difference, affine_removed


def test_simultaneous_epoch_difference_cancels_arbitrary_common_clock_and_wraps():
    fs = 2400000.
    t = np.linspace(0, 40, 101)
    one = .0003+.000002*t
    delta = .0006+.000004*t+.00000004*t*t
    clock = np.random.default_rng(4).normal(0, .001, len(t))
    first = np.mod(one+clock, PERIOD)*fs
    second = np.mod(one+delta+clock, PERIOD)*fs
    recovered = epoch_difference(first, second, fs)
    np.testing.assert_allclose(recovered-recovered[0], delta-delta[0], rtol=0, atol=1e-17)


def test_clock_affine_removal_preserves_curvature_and_removes_only_two_modes():
    t = np.linspace(0, 40, 101)
    values = np.sin(t/10)*1e-6
    residual, _ = affine_removed(t, values)
    shifted, _ = affine_removed(t, values+1e-3+2e-7*t)
    np.testing.assert_allclose(residual, shifted, rtol=0, atol=1e-18)
    assert np.std(residual) > 1e-7
