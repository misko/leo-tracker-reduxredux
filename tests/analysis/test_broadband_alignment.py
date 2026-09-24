from __future__ import annotations

import numpy as np
import pytest

from leo.analysis.starlink.broadband_alignment import estimate_broadband_alignment


def _case(*, noise: float = 0.05) -> tuple[np.ndarray, float, float, float]:
    rate = 200_000.0
    count = 65_536
    cfo = -31_250.0
    drift = 480.0
    delay = 2.375
    rng = np.random.default_rng(8821)
    source = rng.normal(size=count) + 1j * rng.normal(size=count)
    frequency = np.fft.fftfreq(count)
    delayed = np.fft.ifft(np.fft.fft(source) * np.exp(-2j * np.pi * frequency * delay))
    sample = np.arange(count, dtype=float)
    reference = (count / 2 - 1) / 2
    time = (sample - reference) / rate
    phase = 0.7 + 2 * np.pi * (cfo * time + 0.5 * drift * time**2)
    rx0 = source + noise * (rng.normal(size=count) + 1j * rng.normal(size=count))
    rx1 = delayed * np.exp(1j * phase)
    rx1 += noise * (rng.normal(size=count) + 1j * rng.normal(size=count))
    return np.column_stack((rx0, rx1)), rate, cfo, drift


def test_recovers_cfo_drift_and_validates_on_held_samples() -> None:
    iq, rate, cfo, drift = _case()

    result = estimate_broadband_alignment(
        iq,
        rate,
        receiver_cfo_seed_hz=cfo,
        cfo_search_half_width_hz=2_000,
        block_samples=2048,
        channel_smoothing_bins=5,
    )

    assert result.model.relative_cfo_hz == pytest.approx(cfo, abs=5)
    assert result.model.relative_cfo_rate_hz_s == pytest.approx(drift, abs=80)
    assert result.training.covered_bandwidth_hz <= rate - abs(cfo) + 1
    assert result.held_out.corrected_coherence > 0.85
    assert result.held_out.corrected_coherence > 5 * result.held_out.wrong_time_coherence


def test_physical_overlap_excludes_fft_wrapped_partner_bins() -> None:
    iq, rate, cfo, _ = _case()
    result = estimate_broadband_alignment(
        iq, rate, receiver_cfo_seed_hz=cfo, cfo_search_half_width_hz=2_000, block_samples=2048
    )
    frequency = np.asarray(result.training_frequency_hz)
    mask = np.asarray(result.training_physical_overlap_mask)
    assert np.all(abs(frequency[mask] + result.model.relative_cfo_hz) <= rate / 2)


def test_noise_only_abstains_instead_of_fitting_random_bins() -> None:
    rng = np.random.default_rng(71)
    noise = rng.normal(size=(65_536, 2)) + 1j * rng.normal(size=(65_536, 2))
    with pytest.raises(ValueError, match="coherent physical-overlap"):
        estimate_broadband_alignment(
            noise, 200_000.0, receiver_cfo_seed_hz=-31_250, cfo_search_half_width_hz=2_000
        )


def test_held_only_perturbation_cannot_change_frozen_model_or_mask() -> None:
    iq, rate, cfo, _ = _case()
    changed = iq.copy()
    rng = np.random.default_rng(98)
    changed[len(changed) // 2 :] += 3 * (
        rng.normal(size=changed[len(changed) // 2 :].shape)
        + 1j * rng.normal(size=changed[len(changed) // 2 :].shape)
    )

    baseline = estimate_broadband_alignment(
        iq,
        rate,
        receiver_cfo_seed_hz=cfo,
        cfo_search_half_width_hz=2_000,
        block_samples=2048,
    )
    perturbed = estimate_broadband_alignment(
        changed,
        rate,
        receiver_cfo_seed_hz=cfo,
        cfo_search_half_width_hz=2_000,
        block_samples=2048,
    )

    assert perturbed.model == baseline.model
    assert perturbed.training_physical_overlap_mask == baseline.training_physical_overlap_mask
    assert perturbed.training_bin_coherence == baseline.training_bin_coherence
    assert perturbed.held_out.corrected_coherence < baseline.held_out.corrected_coherence
