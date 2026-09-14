"""Decision-budget research accounting and causal-filter controls; no hardware."""

import numpy as np
import pytest

from tools.investigate_adaptive_decision_budget import (
    decimate,
    decimate_window,
    positive,
    taps_for,
    temporal_windows,
)


@pytest.mark.parametrize("rate", [2_500_000, 5_000_000])
def test_decimator_is_causal_and_records_native_group_delay(rate):
    iq = np.zeros((4096, 2), dtype="int16")
    iq[1024, 0] = 30000
    out, stats = decimate(iq, rate)
    factor = 10_000_000 // rate
    assert out.shape == (4096 // factor, 2)
    assert not np.any(out[: 1024 // factor])
    assert np.argmax(out[:, 0]) * factor == 1024 + stats["group_delay_native_samples"]
    assert stats["clipped_components"] == 0
    assert sum(taps_for(rate)) == pytest.approx(1)


@pytest.mark.parametrize("rate", [2_500_000, 5_000_000])
def test_decimation_preserves_pilot_cfo_band_and_rejects_alias_tone(rate):
    n = np.arange(40000)
    amplitudes = []
    for frequency in (400000, rate * 0.6):
        x = 10000 * np.exp(2j * np.pi * frequency * n / 10_000_000)
        iq = np.rint(np.column_stack((x.real, x.imag))).astype("int16")
        out, _ = decimate(iq, rate)
        amplitudes.append(np.sqrt(np.mean(out[512:].astype(float) ** 2)))
    assert amplitudes[0] > 7000
    assert amplitudes[1] < amplitudes[0] * 0.001


def test_partial_probe_masks_and_positive_thresholds_are_explicit():
    assert temporal_windows("rotating1", 7) == (1,)
    assert temporal_windows("uniform3", 0) == (0, 2, 4)
    c = dict(fractional_complete=1, exact_score=0.175, margin=0.025)
    assert positive(dict(candidate_count=1, candidates=[c]))
    assert not positive(dict(candidate_count=1, candidates=[dict(c, fractional_complete=0)]))
    assert not positive(dict(candidate_count=0, candidates=[c]))


def test_invalid_rate_or_receiver_shape_is_rejected():
    with pytest.raises(ValueError):
        taps_for(10_000_000)
    with pytest.raises(ValueError):
        decimate(np.zeros((32, 2, 2), dtype="int16"), 5_000_000)


@pytest.mark.parametrize("rate", [2_500_000, 5_000_000])
def test_polyphase_matches_full_causal_convolution_on_both_components(rate):
    iq = np.random.default_rng(73).integers(-12000, 12000, (4096, 2), dtype="int16")
    got, _ = decimate(iq, rate)
    factor = 10_000_000 // rate
    expected = np.column_stack(
        [np.convolve(iq[:, c], taps_for(rate))[: len(iq) : factor] for c in range(2)]
    )
    np.testing.assert_array_equal(got, np.rint(expected).astype("int16"))


@pytest.mark.parametrize("rate", [2_500_000, 5_000_000])
def test_sparse_filter_keeps_real_history_and_exact_sample_alignment(rate):
    iq = np.random.default_rng(93).integers(-12000, 12000, (1_200_000, 2), dtype="int16")
    full, _ = decimate(iq, rate)
    for window in (0, 1, 5):
        sparse, _ = decimate_window(iq, rate, window)
        np.testing.assert_array_equal(sparse, full[window * rate // 50 : (window + 1) * rate // 50])
