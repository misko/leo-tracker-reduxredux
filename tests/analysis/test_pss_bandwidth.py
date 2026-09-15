"""Independent spectral projection, true CFO acquisition and geometry controls."""

import numpy as np
import pytest

from leo.analysis.starlink.pss_bandwidth import PssCaptureBand, acquire_pss_band, band_template
from leo.analysis.starlink.pss_timing import pss_native_time_samples, pss_subband_template


def test_partial_edge_overlap_preserves_native_grid():
    band = PssCaptureBand(10e6, 115_195_312.5, -5e6, 5e6)
    assert band.overlap_hz(0) == (-5e6, 4_804_687.5)
    assert band.overlap_hz(-500_000) == (-5e6, 4_304_687.5)
    template = band_template(band, 0)
    assert len(template.samples) == 44
    assert np.linalg.norm(template.samples) == pytest.approx(1, abs=1e-6)
    assert not template.samples.flags.writeable
    with pytest.raises(ValueError):
        template.samples.setflags(write=True)
    with pytest.raises(ValueError, match="outside"):
        pss_subband_template(10e6, slice_center_offset_hz=115_195_312.5)


@pytest.mark.parametrize("center", [-115_195_312.5, 0, 115_195_312.5])
def test_projection_matches_independent_high_rate_filtered_reference(center):
    # Independent IFFT reconstruction at 240 MHz, followed by integer sampling.
    n = 131072
    band = PssCaptureBand(10e6, center, -4e6, 4e6)
    native = pss_native_time_samples()
    freq = np.fft.fftfreq(n, 1 / 240e6)
    spectrum = np.fft.fft(native, n)
    spectrum[np.abs(freq - center) >= 4e6] = 0
    high_rate = np.fft.ifft(spectrum)
    indexes = np.arange(44) * 24
    expected = high_rate[indexes] * np.exp(-2j * np.pi * center * indexes / 240e6)
    expected /= np.linalg.norm(expected)
    observed = band_template(band, 0, fft_size=131072).samples
    np.testing.assert_allclose(observed, expected, atol=2e-7)
    coarse = band_template(band, 0).samples
    assert abs(np.vdot(coarse, expected)) > 0.999


@pytest.mark.parametrize("rate", [2.5e6, 5e6, 10e6, 15e6, 30e6])
def test_blind_bank_recovers_injected_nonzero_cfo_and_epoch(rate):
    band = PssCaptureBand(rate, 115_195_312.5, -rate / 2, rate / 2)
    cfo = -400_000.0
    # High-resolution oracle projection, different quadrature from acquisition.
    pulse = band_template(band, cfo, fft_size=131072).samples
    pulse = pulse * np.exp(2j * np.pi * cfo * np.arange(len(pulse)) / rate)
    rng = np.random.default_rng(512)
    count = round(rate * 0.012)
    iq = (rng.normal(size=count) + 1j * rng.normal(size=count)).astype("complex64")
    epoch = round(rate * 0.00037)
    for start in range(epoch, count - len(pulse), round(rate / 750)):
        iq[start : start + len(pulse)] += 25 * pulse
    result = acquire_pss_band(
        iq,
        band,
        device_sample_start=1_000_000,
        continuity_segment_index=8,
        frequency_offsets_hz=(-400_000.0, 0.0, 400_000.0),
    )
    assert len(result.hypotheses) == 3
    right = result.hypotheses[0]
    assert right.qualified_candidates
    assert abs(right.qualified_candidates[0].epoch_sample - epoch) <= 2
    assert right.qualified_candidates[0].frequency_offset_hz == cfo
    assert right.global_device_sample_start == 1_000_000


def test_no_overlap_and_invalid_band_are_explicit():
    with pytest.raises(ValueError, match="Nyquist"):
        PssCaptureBand(10e6, 0, -6e6, 5e6)
    band = PssCaptureBand(10e6, 200e6, -5e6, 5e6)
    result = acquire_pss_band(
        np.ones(1000),
        band,
        device_sample_start=0,
        continuity_segment_index=0,
        frequency_offsets_hz=(0.0,),
    )
    assert not result.hypotheses
    assert result.unsupported_offsets_hz == (0.0,)


def test_measured_zero_response_is_not_normalized_into_a_signal():
    band = PssCaptureBand(10e6, 0, -5e6, 5e6, ((-5e6, 0, 0), (5e6, 0, 0)))
    with pytest.raises(ValueError, match="energy"):
        band_template(band, 0)


@pytest.mark.parametrize("kind", ["noise", "tone"])
@pytest.mark.parametrize("rate", [2_500_000, 10_000_000])
def test_full_bank_negative_controls(kind, rate):
    from leo.analysis.starlink.pss_tracker import PssTracker, observations_from_search

    rng = np.random.default_rng(417)
    count = round(rate * 0.02)
    iq = (rng.normal(size=count) + 1j * rng.normal(size=count)).astype("complex64")
    if kind == "tone":
        iq += 10 * np.exp(2j * np.pi * 250_000 * np.arange(count) / rate)
    band = PssCaptureBand(rate, 115_195_312.5, -rate / 2, rate / 2)
    tracker = PssTracker("negative")
    for block in range(3):
        if block:
            iq = (rng.normal(size=count) + 1j * rng.normal(size=count)).astype("complex64")
            if kind == "tone":
                iq += 10 * np.exp(2j * np.pi * 250_000 * np.arange(count) / rate)
        result = acquire_pss_band(
            iq,
            band,
            device_sample_start=block * rate,
            continuity_segment_index=block,
            frequency_offsets_hz=tuple(float(f) for f in range(-1200000, 1200001, 200000)),
        )
        # Individual peaks may exceed z=6 after a bank search: qualification
        # is candidate-only, and cannot by itself establish a track.
        assert all(h.candidate_only for h in result.hypotheses)
        estimate = tracker.update("negative", block + 0.01, observations_from_search(result))
        assert estimate.state != "tracking"


def test_complex_receiver_response_changes_template_without_changing_sample_grid():
    flat = PssCaptureBand(10e6, 0, -5e6, 5e6)
    gain = PssCaptureBand(10e6, 0, -5e6, 5e6, ((-5e6, 0, 2), (5e6, 0, 2)))
    np.testing.assert_allclose(
        band_template(gain, 0).samples, 1j * band_template(flat, 0).samples, atol=2e-7
    )


def test_fine_bank_reacquires_between_coarse_bins():
    from leo.analysis.starlink.pss_bandwidth import acquire_pss_coarse_to_fine

    rate = 10_000_000
    band = PssCaptureBand(rate, 115_195_312.5, -5e6, 5e6)
    cfo = -475_000.0
    pulse = band_template(band, cfo, fft_size=131072).samples
    pulse = pulse * np.exp(2j * np.pi * cfo * np.arange(len(pulse)) / rate)
    rng = np.random.default_rng(17)
    values = (rng.normal(size=120000) + 1j * rng.normal(size=120000)).astype("complex64")
    for start in range(3700, len(values) - len(pulse), round(rate / 750)):
        values[start : start + len(pulse)] += 50 * pulse
    result = acquire_pss_coarse_to_fine(
        values,
        band,
        device_sample_start=0,
        continuity_segment_index=0,
        coarse_offsets_hz=(-600000.0, -400000.0, 0.0),
    )
    frequencies = [h.nominal_frequency_offset_hz for h in result.hypotheses]
    assert cfo in frequencies
    assert len(frequencies) == len(set(frequencies)) <= 257
    best = max(
        (c for h in result.hypotheses for c in h.qualified_candidates), key=lambda c: c.folded_score
    )
    assert abs(best.frequency_offset_hz - cfo) <= 25000
