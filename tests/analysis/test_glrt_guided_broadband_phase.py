from __future__ import annotations

import numpy as np
import pytest

from leo.analysis.starlink.glrt_guided_broadband_phase import (
    GuidePoint,
    estimate_glrt_guided_broadband_phase,
)


def _case() -> tuple[np.ndarray, float, tuple[GuidePoint, ...]]:
    rate, count = 200_000.0, 65_536
    cfo, drift = -31_250.0, 420.0
    rng = np.random.default_rng(55)
    source = rng.normal(size=count) + 1j * rng.normal(size=count)
    sample = np.arange(count, dtype=float)
    reference = count / 4
    time = (sample - reference) / rate
    rx1 = source * np.exp(1j * (0.4 + 2 * np.pi * (cfo * time + 0.5 * drift * time**2)))
    iq = np.column_stack((source, rx1))
    guides = tuple(
        GuidePoint(float(s), cfo + drift * (s - reference) / rate, 2.0)
        for s in np.linspace(2_000, count / 2 - 2_000, 7)
    )
    return iq, rate, guides


def test_guides_refine_frequency_and_phase_with_held_validation() -> None:
    iq, rate, guides = _case()
    result = estimate_glrt_guided_broadband_phase(
        iq,
        rate,
        guides,
        broadband_cfo_seed_hz=-31_250,
        block_samples=2048,
    )
    assert abs(result.map_model.relative_cfo_hz + 31_250) < 1
    assert abs(result.map_model.relative_cfo_rate_hz_s - 420) < 10
    assert result.held_out.coherence > 0.9
    assert result.selected_guide_count == len(guides)
    assert result.map_model.conditional_phase_standard_error_rad > 0
    assert "four_contiguous_group" in result.map_model.phase_uncertainty_kind


def test_held_only_change_does_not_change_training_models() -> None:
    iq, rate, guides = _case()
    changed = iq.copy()
    changed[len(changed) // 2 :, 1] *= np.exp(1.2j)
    baseline = estimate_glrt_guided_broadband_phase(
        iq, rate, guides, broadband_cfo_seed_hz=-31_250, block_samples=2048
    )
    perturbed = estimate_glrt_guided_broadband_phase(
        changed, rate, guides, broadband_cfo_seed_hz=-31_250, block_samples=2048
    )
    assert perturbed.data_only == baseline.data_only
    assert perturbed.map_model == baseline.map_model
    assert abs(perturbed.held_out.phase_rad - baseline.held_out.phase_rad) > 1


def test_collectively_biased_guides_are_rejected_instead_of_pulling_map() -> None:
    iq, rate, guides = _case()
    biased = tuple(
        GuidePoint(guide.sample, guide.relative_frequency_hz + 1_000, guide.sigma_hz)
        for guide in guides
    )

    result = estimate_glrt_guided_broadband_phase(
        iq, rate, biased, broadband_cfo_seed_hz=-31_250, block_samples=2048
    )

    assert result.selected_guide_count == 0
    assert result.rejected_guide_count == len(guides)
    assert result.map_model.relative_cfo_hz == result.data_only.relative_cfo_hz
    assert result.map_model.relative_cfo_rate_hz_s == result.data_only.relative_cfo_rate_hz_s


def test_optional_guide_bias_uses_frequency_changes_without_forcing_cfo() -> None:
    iq, rate, guides = _case()
    biased = tuple(
        GuidePoint(guide.sample, guide.relative_frequency_hz + 200, guide.sigma_hz)
        for guide in guides
    )

    result = estimate_glrt_guided_broadband_phase(
        iq,
        rate,
        biased,
        broadband_cfo_seed_hz=-31_250,
        block_samples=2048,
        fit_guide_bias=True,
    )

    assert result.map_model.guide_bias_hz == pytest.approx(200, abs=10)
    assert result.map_model.relative_cfo_hz == pytest.approx(-31_250, abs=1)
    assert result.map_model.relative_cfo_rate_hz_s == pytest.approx(420, abs=10)
