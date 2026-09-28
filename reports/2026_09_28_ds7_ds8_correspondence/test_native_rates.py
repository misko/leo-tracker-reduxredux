"""Scientific guards for native-rate bandwidth and incomplete-word handling."""

import numpy as np
import pytest
from native_rate_decode import calibrate, supported_bins
from rate_validation import retained_bins
from tcodes import bit_word, demodulate, fit_code, geometry, slots


@pytest.mark.parametrize("edge", ["upper", "lower"])
def test_centered_bandwidth_limits_slot_coverage(edge):
    for rate, expected in [(7500000, 60), (5000000, 60), (2500000, 30)]:
        mapping = slots(retained_bins(edge, rate), np.arange(14, 78))
        assert len(np.unique(mapping)) == expected


def test_receiver_frequency_offset_changes_available_slots():
    bins, _, center = geometry("upper")
    a = supported_bins(bins, center, 2500000, -218938)
    b = supported_bins(bins, center, 2500000, 459252)
    assert a.tolist() == [496, 497]
    assert b.tolist() == [485, 486, 487]
    ma, mb = [np.unique(slots(k, np.arange(14, 78))) for k in [a, b]]
    assert len(np.union1d(ma, mb)) == 60
    assert len(np.intersect1d(ma, mb)) == 15


def test_missing_positions_are_unknown_not_zero_bits():
    mapping = slots(np.array([496, 497]), np.arange(14, 78))
    truth = np.random.default_rng(42).choice([-1, 1], 60)
    code, _, count = fit_code(truth[mapping].astype(complex), mapping)
    assert np.array_equal(code[count > 0], truth[count > 0])
    assert bit_word(code).count("?") == 30


@pytest.mark.parametrize("rate", [7500000, 5000000, 2500000])
def test_demodulator_preserves_native_tone_at_each_rate(rate):
    _, _, center = geometry("upper")
    k, cfo = 489, 100000
    frequency = k * 234375 - center + cfo
    x = np.exp(2j * np.pi * frequency * np.arange(round(rate * 0.0014)) / rate)
    symbols = demodulate(x, rate, 0, cfo, center)
    assert np.all(np.argmax(abs(symbols), axis=1) == k)
    assert np.allclose(abs(symbols[:, k]), 1024, rtol=0.02)


def test_pilot_subset_calibration_does_not_require_unreceived_pilots():
    rng = np.random.default_rng(55)
    pb = np.arange(488, 495)
    pilot = np.exp(0.5j * np.pi * rng.integers(0, 4, (300, len(pb))))
    ideal = np.ones((301, 1024), complex)
    ideal[1:, pb] = pilot
    response = 3 * np.exp(1j * (0.03 * (np.arange(1024) - pb.mean()) + 0.4))
    carrier = np.exp(2j * np.pi * 1300 * (np.arange(301) - 1) * 4.4e-6)
    corrected, diagnostic = calibrate(ideal * response * carrier[:, None], pilot, pb)
    assert diagnostic["held_pilot_coherence"] > 0.999999
    assert np.allclose(corrected[:, 476:508], ideal[:, 476:508], atol=1e-5)
