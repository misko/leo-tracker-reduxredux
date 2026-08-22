from __future__ import annotations

import numpy as np
import pytest

from leo.analysis.qam import analyze_pilot_phase_slope
from leo.analysis.qam.pilot import _estimate_phase_slope_frames
from leo.analysis.starlink import NumericalStatus, qin_edge_pilot_frame
from leo.analysis.starlink.templates import (
    CONTROL_SYMBOL_ROLL,
    FRAME_RATE_HZ,
    OFDM_SYMBOL_DURATION_S,
    qin_edge_pilot_symbols,
)
from leo.contracts.states import StarlinkEdge

RATE = 2_500_000.0
EPOCH = 37


def test_phase_slope_recovers_each_frame_with_arbitrary_phase_and_channel() -> None:
    generator = np.random.default_rng(0x51_0FE)
    expected = qin_edge_pilot_symbols(StarlinkEdge.LOWER)
    control = qin_edge_pilot_symbols(
        StarlinkEdge.LOWER,
        symbol_roll=CONTROL_SYMBOL_ROLL,
    )
    times_s = (np.arange(300, dtype=float) + 2.5) * OFDM_SYMBOL_DURATION_S
    times_s -= np.mean(times_s)
    frequencies_hz = np.asarray([-875.0, -310.0, 0.0, 425.0, 1_190.0])
    frame_phases_rad = np.asarray([-2.4, 0.3, 2.8, -0.7, 1.6])
    channel = np.asarray(
        [
            0.4 * np.exp(0.8j),
            1.2 * np.exp(-1.1j),
            0.8 * np.exp(2.2j),
            1.0,
            0.5j,
            -0.9j,
            0.7 * np.exp(0.3j),
            1.4 * np.exp(-0.7j),
        ]
    )
    pilots = (
        expected[None, :, :]
        * channel[None, None, :]
        * np.exp(
            1j
            * (
                frame_phases_rad[:, None, None]
                + 2 * np.pi * frequencies_hz[:, None, None] * times_s[None, :, None]
            )
        )
    )
    pilots += (
        0.08
        * (generator.normal(size=pilots.shape) + 1j * generator.normal(size=pilots.shape))
        / np.sqrt(2)
    )

    result = _estimate_phase_slope_frames(
        pilots,
        expected,
        control,
        tuple(range(len(frequencies_hz))),
        sample_rate_hz=RATE,
        absolute_cfo_hz=100_000.0,
        maximum_residual_cfo_hz=2_000.0,
    )

    assert result.status is NumericalStatus.COMPLETE
    assert result.phase_continuity_assumed is False
    np.testing.assert_allclose(
        [frame.residual_cfo_hz for frame in result.frames],
        frequencies_hz,
        atol=2.0,
    )
    assert all(frame.frequency_uncertainty_hz < 1.0 for frame in result.frames)
    assert all(frame.coherence_margin > 0.98 for frame in result.frames)
    assert all(frame.phase_residual_rms_rad < 0.03 for frame in result.frames)

    # Phase is correctly recovered up to one arbitrary common channel phase.
    measured = np.asarray([frame.phase_at_reference_rad for frame in result.frames])
    measured_relative = np.angle(np.exp(1j * (measured - measured[0])))
    expected_relative = np.angle(np.exp(1j * (frame_phases_rad - frame_phases_rad[0])))
    phase_error = np.angle(np.exp(1j * (measured_relative - expected_relative)))
    assert np.max(np.abs(phase_error)) < 0.01


def test_raw_phase_slope_uses_all_symbols_without_connecting_frame_phase() -> None:
    template = qin_edge_pilot_frame(RATE, StarlinkEdge.LOWER)
    samples = np.zeros(14_000, dtype=np.complex128)
    indexes = np.arange(template.size)
    acquired_cfo_hz = 200_000.0
    residual_cfo_hz = np.asarray([-875.0, -250.0, 420.0, 1_100.0])
    phases_rad = np.asarray([-2.0, 1.1, -0.4, 2.6])
    for frame, (frequency_hz, phase_rad) in enumerate(
        zip(residual_cfo_hz, phases_rad, strict=True)
    ):
        start = EPOCH + round(frame * RATE / FRAME_RATE_HZ)
        samples[start + indexes] += template * np.exp(
            1j
            * (phase_rad + 2 * np.pi * (acquired_cfo_hz + frequency_hz) * (start + indexes) / RATE)
        )

    result = analyze_pilot_phase_slope(
        samples,
        RATE,
        epoch_sample=EPOCH,
        absolute_cfo_hz=acquired_cfo_hz,
        edge=StarlinkEdge.LOWER,
    )

    assert result.status is NumericalStatus.COMPLETE
    np.testing.assert_allclose(
        [frame.residual_cfo_hz for frame in result.frames],
        residual_cfo_hz,
        atol=0.3,
    )
    assert all(frame.symbol_count == 300 for frame in result.frames)
    assert all(frame.coherence_margin > 0.97 for frame in result.frames)
    assert all(frame.phase_residual_rms_rad < 0.03 for frame in result.frames)
    assert result.aggregate_absolute_cfo_hz == pytest.approx(
        acquired_cfo_hz + np.median(residual_cfo_hz),
        abs=0.3,
    )


def test_symbol_rolled_capture_wins_the_negative_control() -> None:
    control_template = qin_edge_pilot_frame(
        RATE,
        StarlinkEdge.UPPER,
        symbol_roll=CONTROL_SYMBOL_ROLL,
    )
    samples = np.zeros(14_000, dtype=np.complex128)
    indexes = np.arange(control_template.size)
    for frame in range(4):
        start = EPOCH + round(frame * RATE / FRAME_RATE_HZ)
        samples[start + indexes] += control_template

    result = analyze_pilot_phase_slope(
        samples,
        RATE,
        epoch_sample=EPOCH,
        absolute_cfo_hz=0.0,
        edge=StarlinkEdge.UPPER,
    )

    assert result.status is NumericalStatus.COMPLETE
    assert all(frame.exact_coherence < 0.01 for frame in result.frames)
    assert all(frame.control_coherence > 0.97 for frame in result.frames)
    assert all(frame.coherence_margin < -0.96 for frame in result.frames)


def test_dropped_frame_is_excluded_from_the_aggregate() -> None:
    expected = qin_edge_pilot_symbols(StarlinkEdge.LOWER)
    control = qin_edge_pilot_symbols(
        StarlinkEdge.LOWER,
        symbol_roll=CONTROL_SYMBOL_ROLL,
    )
    times_s = (np.arange(300, dtype=float) + 2.5) * OFDM_SYMBOL_DURATION_S
    times_s -= np.mean(times_s)
    frequencies_hz = np.asarray([-600.0, -200.0, 200.0, 600.0])
    pilots = expected[None, :, :] * np.exp(
        2j * np.pi * frequencies_hz[:, None, None] * times_s[None, :, None]
    )
    pilots[2] = 0

    result = _estimate_phase_slope_frames(
        pilots,
        expected,
        control,
        (0, 1, 2, 3),
        sample_rate_hz=RATE,
        absolute_cfo_hz=0.0,
        maximum_residual_cfo_hz=2_000.0,
    )

    assert result.frames[2].exact_coherence == 0.0
    assert result.frames[2].coherence_margin == 0.0
    assert result.aggregate_residual_cfo_hz == pytest.approx(-200.0, abs=0.3)


def test_phase_slope_null_and_short_windows_have_no_false_frames() -> None:
    short = analyze_pilot_phase_slope(
        np.ones(100, dtype=np.complex128),
        RATE,
        epoch_sample=0,
        absolute_cfo_hz=0.0,
        edge=StarlinkEdge.LOWER,
    )
    null = analyze_pilot_phase_slope(
        np.zeros(14_000, dtype=np.complex128),
        RATE,
        epoch_sample=0,
        absolute_cfo_hz=0.0,
        edge=StarlinkEdge.LOWER,
    )

    assert short.status is NumericalStatus.INSUFFICIENT and not short.frames
    assert null.status is NumericalStatus.NO_RESULT and not null.frames
    assert short.aggregate_absolute_cfo_hz is None
    assert null.aggregate_absolute_cfo_hz is None

    with pytest.raises(ValueError, match="Nyquist"):
        analyze_pilot_phase_slope(
            np.ones(14_000, dtype=np.complex128),
            RATE,
            epoch_sample=0,
            absolute_cfo_hz=0.0,
            edge=StarlinkEdge.LOWER,
            maximum_residual_cfo_hz=200_000.0,
        )
