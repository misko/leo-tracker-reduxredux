from __future__ import annotations

import math

import numpy as np
import pytest

from leo.analysis.qam import (
    PilotFrameCfoConfig,
    estimate_edge_pilot_frame_cfo,
)
from leo.analysis.qam.pilot import _estimate_edge_pilot_frame_cfo_from_cubes
from leo.analysis.starlink import NumericalStatus, qin_edge_pilot_frame
from leo.analysis.starlink.templates import (
    CONTROL_SYMBOL_ROLL,
    OFDM_SYMBOL_DURATION_S,
    StarlinkEdge,
    qin_edge_pilot_symbols,
)

RATE = 2_500_000.0


def test_frame_cfo_recovers_one_acquisition_bound_raw_frame() -> None:
    frame_start = 1_234_567
    template = np.asarray(qin_edge_pilot_frame(RATE, StarlinkEdge.LOWER), np.complex128)
    frame_content = round(302 * RATE * OFDM_SYMBOL_DURATION_S)
    samples = np.zeros(frame_content + 2, dtype=np.complex128)
    indexes = np.arange(frame_content)
    acquisition_cfo_hz = 200_000.0
    residual_cfo_hz = 317.4
    samples[1 + indexes] = template[:frame_content] * np.exp(
        2j * np.pi * (acquisition_cfo_hz + residual_cfo_hz) * (frame_start + indexes) / RATE
    )

    result = estimate_edge_pilot_frame_cfo(
        samples,
        RATE,
        frame_start_sample=frame_start,
        acquisition_absolute_cfo_hz=acquisition_cfo_hz,
        edge=StarlinkEdge.LOWER,
    )

    assert result.status is NumericalStatus.COMPLETE
    assert result.measurement_supported
    assert result.rejection_reasons == ()
    assert result.residual_cfo_hz == pytest.approx(residual_cfo_hz, abs=0.4)
    assert result.absolute_cfo_hz == pytest.approx(
        acquisition_cfo_hz + residual_cfo_hz,
        abs=0.4,
    )
    assert result.exact_coherence is not None and result.exact_coherence > 0.97
    assert result.coherence_margin is not None and result.coherence_margin > 0.96
    assert result.even_odd_disagreement_hz is not None
    assert result.even_odd_disagreement_hz < 0.5
    assert result.timing_spread_hz is not None and result.timing_spread_hz < 3.0
    assert result.half_frame_difference_z is not None
    assert result.half_frame_difference_z < 1.0
    assert result.tone_deletion_spread_hz is not None
    assert result.tone_deletion_spread_hz < 1.0


def test_coherent_one_tone_spur_is_rejected_by_deletion_influence() -> None:
    expected = qin_edge_pilot_symbols(StarlinkEdge.LOWER)
    control = qin_edge_pilot_symbols(
        StarlinkEdge.LOWER,
        symbol_roll=CONTROL_SYMBOL_ROLL,
    )
    times_s = (np.arange(300, dtype=float) - 149.5) * OFDM_SYMBOL_DURATION_S
    truth_hz = 200.0
    matched = 0.2 * np.exp(2j * np.pi * truth_hz * times_s[:, None]) * np.ones((1, 8))
    matched[:, 3] += 4.5 * np.exp(2j * np.pi * (truth_hz + 1_200.0) * times_s)
    pilots = matched * expected

    result = _estimate_edge_pilot_frame_cfo_from_cubes(
        (pilots, pilots, pilots),
        expected,
        control,
        frame_start_sample=1,
        reference_sample=1_663.5,
        acquisition_absolute_cfo_hz=0.0,
        config=PilotFrameCfoConfig(),
    )

    assert result.status is NumericalStatus.COMPLETE
    assert result.residual_cfo_hz == pytest.approx(truth_hz + 1_200.0, abs=10.0)
    assert not result.measurement_supported
    assert result.rejection_reasons == ("tone_deletion_shift_above_maximum",)
    assert result.tone_deletion_spread_hz is not None
    assert result.tone_deletion_spread_hz > 1_000.0


def test_published_coherent_spur_trials_have_no_deletion_gate_false_accepts() -> None:
    """Freeze the exact 40-trial contamination regression used by the report."""

    generator = np.random.default_rng(0xCF0_2026)
    expected = qin_edge_pilot_symbols(StarlinkEdge.LOWER)
    control = qin_edge_pilot_symbols(
        StarlinkEdge.LOWER,
        symbol_roll=CONTROL_SYMBOL_ROLL,
    )
    scenarios = (
        ("clean high SNR", 0.12),
        ("clean medium SNR", 0.35),
        ("clean low SNR", 0.80),
        ("15% symbol outliers", 0.25),
        ("one coherent tone spur", 0.25),
    )
    ordinary_failures = 0
    baseline_false_accepts = 0
    deletion_catches = 0
    deletion_false_accept_catches = 0
    for scenario, noise_sigma in scenarios:
        for _ in range(40):
            truth_hz = float(generator.uniform(-1_500.0, 1_500.0))
            matched, _ = _synthetic_matched_frame(
                generator,
                frequency_hz=truth_hz,
                noise_sigma=noise_sigma,
                scenario=scenario,
            )
            if scenario != "one coherent tone spur":
                continue
            pilots = matched * expected
            result = _estimate_edge_pilot_frame_cfo_from_cubes(
                (pilots, pilots, pilots),
                expected,
                control,
                frame_start_sample=1,
                reference_sample=1_663.5,
                acquisition_absolute_cfo_hz=0.0,
                config=PilotFrameCfoConfig(),
            )
            assert result.residual_cfo_hz is not None
            failed = abs(result.residual_cfo_hz - truth_hz) > 100.0
            if not failed:
                continue
            ordinary_failures += 1
            deletion_rejected = "tone_deletion_shift_above_maximum" in result.rejection_reasons
            deletion_catches += deletion_rejected
            other_rejections = tuple(
                reason
                for reason in result.rejection_reasons
                if reason != "tone_deletion_shift_above_maximum"
            )
            if not other_rejections:
                baseline_false_accepts += 1
                deletion_false_accept_catches += deletion_rejected

    assert ordinary_failures == 36
    assert baseline_false_accepts == 3
    assert deletion_catches == ordinary_failures
    assert deletion_false_accept_catches == baseline_false_accepts


def test_frame_cfo_requires_guards_and_returns_a_typed_null() -> None:
    template = np.asarray(qin_edge_pilot_frame(RATE, StarlinkEdge.UPPER), np.complex128)
    frame_content = round(302 * RATE * OFDM_SYMBOL_DURATION_S)
    with pytest.raises(ValueError, match="one-sample guards"):
        estimate_edge_pilot_frame_cfo(
            template,
            RATE,
            frame_start_sample=1,
            acquisition_absolute_cfo_hz=0.0,
            edge=StarlinkEdge.UPPER,
        )

    result = estimate_edge_pilot_frame_cfo(
        np.zeros(frame_content + 2, dtype=np.complex128),
        RATE,
        frame_start_sample=1,
        acquisition_absolute_cfo_hz=0.0,
        edge=StarlinkEdge.UPPER,
    )
    assert result.status is NumericalStatus.NO_RESULT
    assert not result.measurement_supported
    assert result.rejection_reasons == ("zero_pilot_energy",)
    assert result.absolute_cfo_hz is None
    assert result.tone_deletion_spread_hz is None

    with pytest.raises(ValueError, match="finite and positive"):
        PilotFrameCfoConfig(maximum_tone_deletion_shift_hz=math.nan)


def _synthetic_matched_frame(
    generator: np.random.Generator,
    *,
    frequency_hz: float,
    noise_sigma: float,
    scenario: str,
) -> tuple[np.ndarray, np.ndarray]:
    times_s = (np.arange(300, dtype=float) - 149.5) * OFDM_SYMBOL_DURATION_S
    channel = generator.uniform(0.45, 1.55, size=8) * np.exp(
        1j * generator.uniform(-np.pi, np.pi, size=8)
    )
    values = channel[None, :] * np.exp(2j * np.pi * frequency_hz * times_s[:, None])
    values += (
        noise_sigma
        / np.sqrt(2.0)
        * (generator.normal(size=values.shape) + 1j * generator.normal(size=values.shape))
    )
    if scenario == "15% symbol outliers":
        indexes = generator.choice(len(times_s), size=45, replace=False)
        values[indexes] += 3.5 * np.exp(
            1j * generator.uniform(-np.pi, np.pi, size=(len(indexes), 8))
        )
    elif scenario == "one coherent tone spur":
        tone = int(generator.integers(0, 8))
        spur_frequency_hz = frequency_hz + generator.choice((-1_200.0, 1_200.0))
        values[:, tone] += 4.5 * np.exp(
            1j * (generator.uniform(-np.pi, np.pi) + 2.0 * np.pi * spur_frequency_hz * times_s)
        )
    return values, times_s
