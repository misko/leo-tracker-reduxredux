"""Independent high-rate fixtures; no radio or concrete storage required."""

import numpy as np
import pytest
from scipy import signal

from leo.analysis.starlink.partial_band import (
    _search,
    analyze_partial_band_probe,
    filtered_replicas,
    frame_partition,
    projection_scores,
)
from leo.analysis.starlink.templates import edge_frequencies_hz, qin_edge_pilot_symbols
from leo.contracts.partial_band import PartialBandConfigurationV1


def synthesize(
    *,
    edge="upper",
    cfo=17300.0,
    epoch=417.375,
    rate=1_250_000,
    amplitude=1.0,
    noise=0.3,
    drift=0.0,
    cutoff=550_000.0,
    seed=12,
    verification_signal=True,
):
    """10 MS/s full-frame source, independent of the production replica builder."""
    high = 10_000_000
    t = np.arange(high // 50) / high
    frame_time = np.remainder(t - epoch / 1_250_000, 1 / 750)
    symbol = np.floor(frame_time / 4.4e-6).astype(int)
    local = frame_time - symbol * 4.4e-6 - 2 / 15 * 1e-6
    valid = (symbol >= 2) & (symbol < 302)
    if not verification_signal:
        valid &= ~((symbol >= 140) & (symbol < 216))
    states = qin_edge_pilot_symbols(edge)
    x = np.zeros(t.size, complex)
    x[valid] = np.sum(
        states[symbol[valid] - 2]
        * np.exp(2j * np.pi * local[valid, None] * edge_frequencies_hz(edge)),
        axis=1,
    ) / np.sqrt(8)
    x *= amplitude * np.exp(2j * np.pi * (cfo * t + 0.5 * drift * t * t))
    rng = np.random.default_rng(seed)
    x += noise * (rng.normal(size=t.size) + 1j * rng.normal(size=t.size))
    taps = signal.firwin(257, cutoff, fs=high, window=("kaiser", 8.0))
    return signal.resample_poly(x, 1, high // rate, window=taps).astype(np.complex64)


def test_grouped_partition_is_reproducible_disjoint_and_complete():
    train, evaluation = frame_partition(42)
    assert (train, evaluation) == frame_partition(42)
    assert len(train) == len(evaluation) == 7
    assert set(train).isdisjoint(evaluation)
    assert set(train) | set(evaluation) == set(range(14))
    assert (train, evaluation) != frame_partition(43)


@pytest.mark.parametrize("edge", ["upper", "lower"])
def test_independent_full_frame_fixture_recovers_frequency_and_fractional_timing(edge):
    cfg = PartialBandConfigurationV1(maximum_cfo_hz=40_000, maximum_candidates=1)
    result = analyze_partial_band_probe(synthesize(edge=edge), edge=edge, configuration=cfg)
    winner = result.candidates[0]
    assert winner.passed
    assert abs(winner.cfo_hz - 17_300) <= 100
    assert abs(winner.epoch_samples - 417.375) <= 0.25
    assert winner.evaluation_score > 5 * winner.conditioned_control_score


def test_fft_search_matches_direct_filtered_projection():
    cfg = PartialBandConfigurationV1(maximum_cfo_hz=40_000, maximum_candidates=1)
    x = synthesize()
    train, _ = frame_partition(cfg.split_seed)
    cfo, epoch, score = _search(x, train, cfg, "upper")[0]
    direct = projection_scores(x, train, [cfo], epoch, cfg, "upper")[0]
    assert score == pytest.approx(direct, rel=2e-5, abs=2e-6)


def test_filtering_precedes_sampling_and_templates_have_unit_energy():
    cfg = PartialBandConfigurationV1()
    bank = filtered_replicas(np.array([0.0, 700_000.0]), edge="upper", configuration=cfg)
    assert bank.shape == (2, 352)
    np.testing.assert_allclose(np.linalg.norm(bank, axis=1), 1.0, atol=1e-6)
    assert not np.allclose(bank[0], bank[1])


def test_zero_and_invalid_probes():
    assert analyze_partial_band_probe(np.zeros(25_000), edge="upper").zero_energy
    with pytest.raises(ValueError, match="20 ms"):
        analyze_partial_band_probe(np.zeros(24_999), edge="upper")
    with pytest.raises(ValueError, match="finite"):
        analyze_partial_band_probe(np.full(25_000, np.nan), edge="upper")


@pytest.mark.parametrize("seed", range(4))
def test_colored_noise_does_not_pass(seed):
    cfg = PartialBandConfigurationV1(maximum_cfo_hz=40_000, maximum_candidates=1)
    result = analyze_partial_band_probe(
        synthesize(amplitude=0.0, seed=seed), edge="upper", configuration=cfg
    )
    assert not any(c.passed for c in result.candidates)


def test_training_pattern_without_independent_evaluation_symbols_is_rejected():
    cfg = PartialBandConfigurationV1(maximum_cfo_hz=40_000, maximum_candidates=1)
    result = analyze_partial_band_probe(
        synthesize(verification_signal=False), edge="upper", configuration=cfg
    )
    assert result.candidates[0].training_score > 0.1
    assert not result.candidates[0].passed


@pytest.mark.parametrize("cfo", [-799300.0, -500300.0, -189300.0, 139300.0, 500300.0, 799300.0])
@pytest.mark.parametrize("edge", ["upper", "lower"])
def test_band_edge_frequency_sweep(cfo, edge):
    cfg = PartialBandConfigurationV1(maximum_candidates=1)
    result = analyze_partial_band_probe(
        synthesize(cfo=cfo, edge=edge), edge=edge, configuration=cfg
    )
    assert result.candidates[0].passed
    assert abs(result.candidates[0].cfo_hz - cfo) <= 100
    assert abs(result.candidates[0].epoch_samples - 417.375) <= 0.25


@pytest.mark.parametrize("cutoff", [500000.0, 580000.0])
def test_filter_mismatch_and_doppler_rate(cutoff):
    cfg = PartialBandConfigurationV1(maximum_cfo_hz=40000, maximum_candidates=1)
    result = analyze_partial_band_probe(
        synthesize(cutoff=cutoff, drift=-4000), edge="upper", configuration=cfg
    )
    assert result.candidates[0].passed
    assert abs(result.candidates[0].cfo_hz - 17300) <= 100


@pytest.mark.parametrize("frequency", [-510000.0, -100000.0, 0.0, 17300.0, 510000.0])
def test_unmodulated_carrier_is_not_a_pilot_detection(frequency):
    x = np.exp(2j * np.pi * frequency * np.arange(25000) / 1250000).astype(np.complex64)
    result = analyze_partial_band_probe(x, edge="upper")
    assert not any(c.passed for c in result.candidates)
