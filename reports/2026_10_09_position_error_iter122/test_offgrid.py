import numpy as np
import pytest
from offgrid import DELTA_HZ, base, signal


def test_zero_phase_exact_legacy_parity():
    expected, occupancy = base.signal(0.001, amplitude=0.25, noise_rms=1, seed=122000)
    actual, found = signal(0.001, 0, amplitude=0.25, seed=122000)
    np.testing.assert_array_equal(actual, expected)
    assert found == occupancy


@pytest.mark.parametrize("phase", [-0.4, 0.4])
def test_ramp_sign_and_noise_not_rotated(phase):
    clean, _ = base.signal(0.02, amplitude=1, noise_rms=0)
    actual, _ = signal(0.02, phase, amplitude=1, seed=122001, noise_rms=0)
    indices = np.flatnonzero(abs(clean) > 0.01)
    ratio = actual[indices] / clean[indices]
    expected = np.exp(2j * np.pi * phase * DELTA_HZ * indices / 2_500_000)
    np.testing.assert_allclose(ratio, expected, rtol=0, atol=1e-14)
    noisy, _ = signal(0.02, phase, amplitude=1, seed=122001)
    noise, _ = signal(0, 0, amplitude=1, seed=122001)
    np.testing.assert_allclose(noisy - actual, noise, rtol=0, atol=1e-14)


def test_mask_and_frequency_ramp_commute():
    full, _ = signal(0.02, 0.2, amplitude=0.25, seed=122001, noise_rms=0)
    partial, _ = signal(0.00015, 0.2, amplitude=0.25, seed=122001, noise_rms=0)
    np.testing.assert_array_equal(partial, full * (np.arange(len(full)) / 2_500_000 < 0.00015))
