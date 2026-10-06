"""DSP coordinate tests independent of saved corpus and score outcomes."""

import numpy as np
from bandwidth_replay import (
    FS,
    filter_decimate,
    fir_taps,
    frame_inventory,
    tone_center_eligible,
    transform_seed,
)


def test_filter_passband_stopband_and_zero_delay():
    n = np.arange(24000)
    nominal = 312500.0
    tone = 700000.0
    x = np.exp(2j * np.pi * (tone + nominal) * n / FS)
    y, _, _ = filter_decimate(x, nominal)
    expected = np.exp(2j * np.pi * tone * np.arange(len(y)) / (FS / 4))
    assert np.max(abs(y[100:-100] - expected[100:-100])) < 1e-4
    high = np.exp(2j * np.pi * (1_500_000 + nominal) * n / FS)
    z, _, _ = filter_decimate(high, nominal)
    assert np.sqrt(np.mean(abs(z[100:-100]) ** 2)) < 1e-4
    assert np.max(abs(fir_taps() - fir_taps()[::-1])) < 1e-15


def test_nominal_signs_and_fractional_epoch_preserve_seconds():
    for nominal in (-312500, 312500):
        for epoch, fraction in ((2213, 0.238656), (1438, -0.7914), (12003, 1.7)):
            ep, fr, cfo = transform_seed(epoch, fraction, nominal + 400000, nominal)
            assert abs((ep + fr) / (FS / 4) - (epoch + fraction) / FS) < 1e-15
            assert cfo == 400000
            assert frame_inventory(200000, FS, epoch, fraction) == frame_inventory(
                50000, FS // 4, ep, fr
            )


def test_closed_tone_center_support_is_not_full_spectral_support():
    assert tone_center_eligible(429687.5)
    assert tone_center_eligible(-429687.5)
    assert not tone_center_eligible(429687.5001)
    assert tone_center_eligible(742187.5, 312500)
    # A finite rectangular OFDM waveform has sidelobes beyond these centers.
    # Eligibility asserts no claim about analog filter amplitude/group delay.


def test_reacquisition_coarse_grid_subset_and_same_physical_budget():
    from reacquire import settings

    full = settings(FS, 800000)
    narrow = settings(FS, 400000)
    low = settings(FS // 4, 400000)

    def grid(c):
        return np.arange(c.residual_cfo_min_hz, c.residual_cfo_max_hz + 1, c.coarse_cfo_step_hz)

    assert set(grid(narrow)) <= set(grid(full))
    assert np.array_equal(grid(narrow), grid(low))
    assert (
        full.retained_candidate_count
        == narrow.retained_candidate_count
        == low.retained_candidate_count
        == 8
    )
    assert full.maximum_probe_samples / FS == low.maximum_probe_samples / (FS / 4) == 0.020
    assert (
        full.candidate_epoch_separation_samples / FS
        == low.candidate_epoch_separation_samples / (FS / 4)
        == 2e-6
    )
