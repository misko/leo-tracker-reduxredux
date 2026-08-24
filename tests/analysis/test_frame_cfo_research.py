from __future__ import annotations

import numpy as np
import pytest

from leo.analysis.research.frame_cfo import (
    differential_phase_cfo,
    ordinary_profile_cfo,
    profiled_coherence,
    robust_profile_cfo,
)


def _frame(
    *,
    seed: int,
    frequency_hz: float,
    noise_sigma: float,
) -> tuple[np.ndarray, np.ndarray]:
    generator = np.random.default_rng(seed)
    times = (np.arange(300, dtype=float) - 149.5) * 4.4e-6
    channel = np.exp(1j * generator.uniform(-np.pi, np.pi, size=8)) * generator.uniform(
        0.5, 1.5, size=8
    )
    values = channel[None, :] * np.exp(2j * np.pi * frequency_hz * times[:, None])
    values += (
        noise_sigma
        / np.sqrt(2.0)
        * (generator.normal(size=values.shape) + 1j * generator.normal(size=values.shape))
    )
    return values, times


def test_profile_estimators_recover_a_sub_bin_frequency() -> None:
    values, times = _frame(seed=3, frequency_hz=731.37, noise_sigma=0.12)

    ordinary = ordinary_profile_cfo(
        values,
        times,
        maximum_residual_cfo_hz=2_000.0,
    )
    robust = robust_profile_cfo(
        values,
        times,
        maximum_residual_cfo_hz=2_000.0,
    )
    differential = differential_phase_cfo(
        values,
        times,
        maximum_residual_cfo_hz=2_000.0,
    )

    assert ordinary.frequency_hz == pytest.approx(731.37, abs=1.0)
    assert robust.frequency_hz == pytest.approx(731.37, abs=1.0)
    assert differential == pytest.approx(731.37, abs=7.0)
    assert ordinary.frequency_hz % 5.0 != pytest.approx(0.0, abs=1e-4)
    assert ordinary.normalized_coherence > 0.98
    assert ordinary.search_boundary is False


def test_robust_profile_rejects_sparse_symbol_and_tone_contamination() -> None:
    values, times = _frame(seed=7, frequency_hz=-613.2, noise_sigma=0.18)
    generator = np.random.default_rng(99)
    contaminated = values.copy()
    corrupt_symbols = generator.choice(len(times), size=54, replace=False)
    contaminated[corrupt_symbols] += 4.5 * np.exp(
        1j * generator.uniform(-np.pi, np.pi, size=(len(corrupt_symbols), 8))
    )
    contaminated[:, 2] += 6.0 * np.exp(2j * np.pi * 1_550.0 * times)

    ordinary = ordinary_profile_cfo(
        contaminated,
        times,
        maximum_residual_cfo_hz=2_000.0,
    )
    robust = robust_profile_cfo(
        contaminated,
        times,
        maximum_residual_cfo_hz=2_000.0,
    )

    assert abs(robust.frequency_hz + 613.2) < abs(ordinary.frequency_hz + 613.2)
    assert robust.frequency_hz == pytest.approx(-613.2, abs=15.0)
    assert robust.heavily_downweighted_symbol_fraction > 0.05
    assert robust.effective_symbol_count < ordinary.effective_symbol_count


def test_profiled_coherence_peaks_near_the_true_frequency() -> None:
    values, times = _frame(seed=11, frequency_hz=412.0, noise_sigma=0.25)

    at_truth = profiled_coherence(values, times, 412.0)
    displaced = profiled_coherence(values, times, 1_412.0)

    assert at_truth > 0.9
    assert at_truth > 4.0 * displaced


def test_frame_cfo_estimators_fail_closed_on_invalid_geometry() -> None:
    values = np.ones((19, 8), dtype=np.complex128)
    times = np.arange(19, dtype=float) * 4.4e-6
    with pytest.raises(ValueError, match="at least 20"):
        ordinary_profile_cfo(values, times, maximum_residual_cfo_hz=2_000.0)
    with pytest.raises(ValueError, match="ambiguous"):
        differential_phase_cfo(
            np.ones((30, 8), dtype=np.complex128),
            np.arange(30, dtype=float) * 4.4e-6,
            maximum_residual_cfo_hz=120_000.0,
        )
