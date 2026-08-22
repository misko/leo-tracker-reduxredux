from __future__ import annotations

import numpy as np
import pytest

from leo.analysis.qam import (
    PilotPhaseDopplerTrackingConfig,
    analyze_contiguous_pilot_phase_doppler_tracking,
    analyze_locked_pilot_phase_doppler_tracking,
    analyze_pilot_phase_doppler_tracking,
)
from leo.analysis.starlink import NumericalStatus, qin_edge_pilot_frame
from leo.analysis.starlink.templates import CONTROL_SYMBOL_ROLL, FRAME_RATE_HZ
from leo.contracts.states import StarlinkEdge

RATE = 2_500_000.0
EPOCH = 37


def _continuous_capture(
    *,
    frame_count: int,
    edge: StarlinkEdge,
    base_cfo_hz: float,
    residual_cfo_hz: float,
    doppler_rate_hz_s: float,
    reset_frame: int | None = None,
    reset_rad: float = 0.0,
    dropped_frames: frozenset[int] = frozenset(),
    symbol_roll: int = 0,
    noise_sigma: float = 0.0,
) -> np.ndarray:
    template = qin_edge_pilot_frame(RATE, edge, symbol_roll=symbol_roll)
    indexes = np.arange(template.size)
    final_start = EPOCH + round((frame_count - 1) * RATE / FRAME_RATE_HZ)
    samples = np.zeros(final_start + template.size + 2, dtype=np.complex128)
    for frame in range(frame_count):
        if frame in dropped_frames:
            continue
        start = EPOCH + round(frame * RATE / FRAME_RATE_HZ)
        time_s = (start + indexes) / RATE
        reset = reset_rad if reset_frame is not None and frame >= reset_frame else 0.0
        phase = (
            0.7
            + reset
            + 2
            * np.pi
            * ((base_cfo_hz + residual_cfo_hz) * time_s + 0.5 * doppler_rate_hz_s * time_s**2)
        )
        samples[start + indexes] += template * np.exp(1j * phase)
    if noise_sigma:
        generator = np.random.default_rng(0xCA_221E2)
        samples += (
            noise_sigma
            * (generator.normal(size=samples.size) + 1j * generator.normal(size=samples.size))
            / np.sqrt(2)
        )
    return samples


def test_pilot_tracker_recovers_continuous_phase_doppler_and_rate() -> None:
    base_cfo_hz = 100_000.0
    residual_cfo_hz = 320.0
    doppler_rate_hz_s = -1_800.0
    samples = _continuous_capture(
        frame_count=30,
        edge=StarlinkEdge.LOWER,
        base_cfo_hz=base_cfo_hz,
        residual_cfo_hz=residual_cfo_hz,
        doppler_rate_hz_s=doppler_rate_hz_s,
        noise_sigma=0.015,
    )

    result = analyze_pilot_phase_doppler_tracking(
        samples,
        RATE,
        epoch_sample=EPOCH,
        absolute_cfo_hz=base_cfo_hz,
        edge=StarlinkEdge.LOWER,
    )

    assert result.status is NumericalStatus.COMPLETE
    assert result.phase_segment_count == 1
    assert result.phase_reset_count == 0
    assert result.phase_update_count == 30
    assert result.frequency_update_count == 30
    assert all(abs(frame.phase_innovation_rad) < 0.05 for frame in result.frames[2:])
    final = result.frames[-1]
    expected_frequency = residual_cfo_hz + doppler_rate_hz_s * final.reference_sample / RATE
    assert final.tracked_residual_cfo_hz == pytest.approx(expected_frequency, abs=1.0)
    assert final.tracked_doppler_rate_hz_s == pytest.approx(doppler_rate_hz_s, abs=25.0)
    assert final.frequency_sigma_hz < final.frequency_uncertainty_hz


def test_contiguous_closed_loop_tracks_beyond_the_initial_residual_search_span() -> None:
    base_cfo_hz = 100_000.0
    residual_cfo_hz = 320.0
    doppler_rate_hz_s = -7_000.0
    samples = _continuous_capture(
        frame_count=180,
        edge=StarlinkEdge.LOWER,
        base_cfo_hz=base_cfo_hz,
        residual_cfo_hz=residual_cfo_hz,
        doppler_rate_hz_s=doppler_rate_hz_s,
    )

    result = analyze_contiguous_pilot_phase_doppler_tracking(
        samples,
        RATE,
        epoch_sample=EPOCH,
        initial_absolute_cfo_hz=base_cfo_hz + 300.0,
        edge=StarlinkEdge.LOWER,
    )

    assert result.phase_segment_count == 1
    assert result.phase_update_count == 180
    final = result.frames[-1]
    expected_frequency = (
        base_cfo_hz + residual_cfo_hz + doppler_rate_hz_s * final.reference_sample / RATE
    )
    # The carrier has moved more than the initial +/-2 kHz residual search
    # would permit without closed-loop NCO steering.
    assert abs(expected_frequency - (base_cfo_hz + 300.0)) > 1_500.0
    assert final.tracked_absolute_cfo_hz == pytest.approx(expected_frequency, abs=1.0)
    assert final.tracked_doppler_rate_hz_s == pytest.approx(doppler_rate_hz_s, abs=25.0)


def test_locked_frame_epochs_reacquire_after_an_unobserved_burst_gap() -> None:
    samples = _continuous_capture(
        frame_count=60,
        edge=StarlinkEdge.LOWER,
        base_cfo_hz=90_000.0,
        residual_cfo_hz=240.0,
        doppler_rate_hz_s=-2_000.0,
    )
    observed_indexes = (*range(10), *range(30, 60))
    starts = tuple(EPOCH + round(index * RATE / FRAME_RATE_HZ) for index in observed_indexes)

    result = analyze_locked_pilot_phase_doppler_tracking(
        samples,
        RATE,
        frame_starts=starts,
        initial_absolute_cfo_hz=90_200.0,
        edge=StarlinkEdge.LOWER,
    )

    assert len(result.frames) == len(starts)
    assert result.phase_reset_count == 1
    assert result.frames[10].phase_reset_detected
    final = result.frames[-1]
    expected = 90_240.0 - 2_000.0 * final.reference_sample / RATE
    assert final.tracked_absolute_cfo_hz == pytest.approx(expected, abs=1.0)


def test_pilot_tracker_preserves_doppler_while_resetting_quadrature_phase_step() -> None:
    samples = _continuous_capture(
        frame_count=24,
        edge=StarlinkEdge.UPPER,
        base_cfo_hz=100_000.0,
        residual_cfo_hz=180.0,
        doppler_rate_hz_s=-500.0,
        reset_frame=10,
        reset_rad=np.pi / 2,
    )

    result = analyze_pilot_phase_doppler_tracking(
        samples,
        RATE,
        epoch_sample=EPOCH,
        absolute_cfo_hz=100_000.0,
        edge=StarlinkEdge.UPPER,
    )

    assert result.phase_segment_count == 2
    assert result.phase_reset_count == 1
    assert not result.frames[10].phase_update_applied
    assert result.frames[11].phase_reset_detected
    assert result.frames[11].frequency_update_applied
    assert result.frames[12].phase_update_applied
    assert result.frames[-1].tracked_doppler_rate_hz_s == pytest.approx(-500.0, abs=30.0)


def test_pilot_tracker_coasts_over_one_drop_and_reacquires_after_long_gap() -> None:
    samples = _continuous_capture(
        frame_count=25,
        edge=StarlinkEdge.LOWER,
        base_cfo_hz=80_000.0,
        residual_cfo_hz=-250.0,
        doppler_rate_hz_s=900.0,
        dropped_frames=frozenset({5, *range(11, 21)}),
    )

    result = analyze_pilot_phase_doppler_tracking(
        samples,
        RATE,
        epoch_sample=EPOCH,
        absolute_cfo_hz=80_000.0,
        edge=StarlinkEdge.LOWER,
    )

    by_index = {frame.frame_index: frame for frame in result.frames}
    assert not by_index[5].phase_update_applied
    assert not by_index[5].frequency_update_applied
    assert by_index[6].phase_update_applied
    assert by_index[21].phase_reset_detected
    assert result.phase_reset_count == 1
    assert by_index[22].phase_update_applied


def test_pilot_tracker_rejects_the_rolled_sequence_and_invalid_configuration() -> None:
    samples = _continuous_capture(
        frame_count=5,
        edge=StarlinkEdge.UPPER,
        base_cfo_hz=0.0,
        residual_cfo_hz=0.0,
        doppler_rate_hz_s=0.0,
        symbol_roll=CONTROL_SYMBOL_ROLL,
    )
    result = analyze_pilot_phase_doppler_tracking(
        samples,
        RATE,
        epoch_sample=EPOCH,
        absolute_cfo_hz=0.0,
        edge=StarlinkEdge.UPPER,
    )

    assert result.status is NumericalStatus.NO_RESULT
    assert not result.frames
    with pytest.raises(ValueError, match="phase sigma"):
        PilotPhaseDopplerTrackingConfig(
            minimum_phase_measurement_sigma_rad=0.5,
            maximum_phase_measurement_sigma_rad=0.1,
        )
