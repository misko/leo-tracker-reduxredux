import numpy as np
import pytest

from reports.ALGO08.v3.split_spectrum_trial import (
    BIN_HZ,
    FFT_SIZE,
    Spectra,
    disagreement,
    resolution_control,
    spectral_peak,
    tau_b,
)


def spectrum(center):
    k = np.arange(FFT_SIZE)
    d = (k-center+FFT_SIZE//2) % FFT_SIZE-FFT_SIZE//2
    return np.exp(-0.01*d*d)


def test_noiseless_bin_resolution_and_fractional_control():
    measured = resolution_control()
    assert measured["centered"]["bin_delta"] == 0
    assert measured["straddled"]["bin_delta"] == 1
    for profile in measured.values():
        assert profile["signed_delta_hz"] == pytest.approx(70, abs=1)
        assert profile["absolute_delta_hz"] == profile["signed_delta_hz"]


def test_circular_half_difference_near_signed_fft_boundary():
    exact = np.stack([spectrum(256.1), spectrum(255.9)])
    rolled = 0.5 * exact
    metric = disagreement(np.stack([exact, rolled]))
    assert metric["bin_delta"] == 0
    assert metric["signed_delta_hz"] == pytest.approx(0.2 * BIN_HZ)
    assert metric["margins"][0] == pytest.approx(0.5*exact[0].max())


def test_remote_peak_ambiguity_and_flat_input():
    two_peaks = np.maximum(spectrum(0), 0.995*spectrum(30))
    peak = spectral_peak(two_peaks)
    assert peak["ambiguous"]
    assert peak["distinct_peak"] == pytest.approx(.995)
    assert spectral_peak(np.zeros(FFT_SIZE)) is None
    assert spectral_peak(np.ones(FFT_SIZE)) is None
    quiet = np.zeros((2, 2, FFT_SIZE))
    assert disagreement(quiet)["absolute_delta_hz"] is None
    assert np.ctypeslib.as_array(Spectra().power).shape == (2, 2, 512)


def test_rank_correlation_preserves_ties():
    assert tau_b([1, 2, 2, 3], [8, 7, 7, 1]) == -1
    assert tau_b([1, 1, 1], [1, 2, 3]) is None
