from __future__ import annotations

import numpy as np
import pytest

from leo.analysis.qam import (
    PilotPntKalmanConfig,
    PilotPntKalmanConfigV2,
    analyze_contiguous_pilot_pnt_kalman,
    analyze_contiguous_pilot_pnt_kalman_v2,
)
from leo.analysis.starlink import NumericalStatus, qin_edge_pilot_frame
from leo.analysis.starlink.templates import CONTROL_SYMBOL_ROLL, FRAME_RATE_HZ
from leo.contracts.states import StarlinkEdge

RATE = 2_500_000.0
EPOCH = 37


def _capture(
    *,
    frame_count: int,
    base_cfo_hz: float,
    residual_cfo_hz: float,
    doppler_rate_hz_s: float,
    ambiguity_bits: tuple[int, ...],
    phase_offsets_rad: tuple[float, ...] | None = None,
    symbol_roll: int = 0,
    noise_sigma: float = 0.0,
) -> np.ndarray:
    template = qin_edge_pilot_frame(
        RATE,
        StarlinkEdge.LOWER,
        symbol_roll=symbol_roll,
    )
    indexes = np.arange(template.size)
    final_start = EPOCH + round((frame_count - 1) * RATE / FRAME_RATE_HZ)
    samples = np.zeros(final_start + template.size + 2, dtype=np.complex128)
    offsets = phase_offsets_rad or (0.0,) * frame_count
    if len(offsets) != frame_count:
        raise ValueError("phase-offset fixture must match frame count")
    for frame in range(frame_count):
        start = EPOCH + round(frame * RATE / FRAME_RATE_HZ)
        time_s = (start + indexes) / RATE
        phase = (
            0.4
            + np.pi * ambiguity_bits[frame]
            + offsets[frame]
            + 2
            * np.pi
            * ((base_cfo_hz + residual_cfo_hz) * time_s + 0.5 * doppler_rate_hz_s * time_s**2)
        )
        samples[start + indexes] += template * np.exp(1j * phase)
    if noise_sigma:
        generator = np.random.default_rng(0xB1A5)
        samples += (
            noise_sigma
            * (generator.normal(size=samples.size) + 1j * generator.normal(size=samples.size))
            / np.sqrt(2)
        )
    return samples


def test_modulo_pi_tracker_preserves_one_state_through_binary_phase_flips() -> None:
    frame_count = 80
    bits = tuple((index // 3 + index // 11) % 2 for index in range(frame_count))
    samples = _capture(
        frame_count=frame_count,
        base_cfo_hz=100_000.0,
        residual_cfo_hz=320.0,
        doppler_rate_hz_s=-1_800.0,
        ambiguity_bits=bits,
        noise_sigma=0.01,
    )

    result = analyze_contiguous_pilot_pnt_kalman(
        samples,
        RATE,
        epoch_sample=EPOCH,
        initial_absolute_cfo_hz=100_300.0,
        edge=StarlinkEdge.LOWER,
        # This discrete fixture inserts every frame at the rounded sample and
        # therefore lacks the sub-sample channel ramp present in real IQ.  The
        # test exercises carrier ambiguity; timing has its own real-corpus
        # audit and is left non-gating here.
        config=PilotPntKalmanConfig(timing_innovation_gate_sigma=100.0),
    )

    assert result.status is NumericalStatus.COMPLETE
    assert result.supported_frame_count == frame_count
    assert result.phase_update_count == frame_count
    assert result.frequency_update_count == frame_count
    assert result.timing_update_count == frame_count
    assert result.reacquisition_count == 0
    assert result.phase_lock_qualified
    assert result.phase_lock_reason == "qualified modulo-pi phase lock"
    assert result.carrier_phase_period_rad == pytest.approx(np.pi)
    assert not result.absolute_carrier_phase_resolved
    assert all(abs(frame.phase_innovation_modulo_pi_rad) < 0.06 for frame in result.frames[2:])
    measured_bits = tuple(frame.phase_ambiguity_bit for frame in result.frames)
    either_global_sign = measured_bits == bits or measured_bits == tuple(1 - bit for bit in bits)
    assert either_global_sign
    final = result.frames[-1]
    expected_frequency = 100_320.0 + -1_800.0 * final.reference_sample / RATE
    assert final.tracked_absolute_cfo_hz == pytest.approx(expected_frequency, abs=1.0)
    assert final.tracked_doppler_rate_hz_s == pytest.approx(-1_800.0, abs=30.0)
    assert abs(final.tracked_fractional_timing_samples) < 0.5


def test_rolled_pilot_is_a_negative_control_and_config_fails_closed() -> None:
    samples = _capture(
        frame_count=8,
        base_cfo_hz=0.0,
        residual_cfo_hz=0.0,
        doppler_rate_hz_s=0.0,
        ambiguity_bits=(0,) * 8,
        symbol_roll=CONTROL_SYMBOL_ROLL,
    )

    result = analyze_contiguous_pilot_pnt_kalman(
        samples,
        RATE,
        epoch_sample=EPOCH,
        initial_absolute_cfo_hz=0.0,
        edge=StarlinkEdge.LOWER,
    )
    assert result.status is NumericalStatus.NO_RESULT
    assert not result.frames

    with pytest.raises(ValueError, match="odd"):
        PilotPntKalmanConfig(fractional_timing_grid_points=100)
    with pytest.raises(ValueError, match="pi/2"):
        PilotPntKalmanConfig(phase_innovation_gate_rad=2.0)


def test_expected_roll_can_run_the_same_null_signal_for_control_accounting() -> None:
    samples = _capture(
        frame_count=8,
        base_cfo_hz=0.0,
        residual_cfo_hz=0.0,
        doppler_rate_hz_s=0.0,
        ambiguity_bits=(0,) * 8,
        symbol_roll=CONTROL_SYMBOL_ROLL,
    )
    result = analyze_contiguous_pilot_pnt_kalman(
        samples,
        RATE,
        epoch_sample=EPOCH,
        initial_absolute_cfo_hz=0.0,
        edge=StarlinkEdge.LOWER,
        expected_symbol_roll=CONTROL_SYMBOL_ROLL,
    )
    assert result.status is NumericalStatus.COMPLETE
    assert result.expected_symbol_roll == CONTROL_SYMBOL_ROLL
    assert result.supported_frame_count == 8
    assert not result.phase_lock_qualified


def test_v2_reacquires_phase_without_waiting_for_a_frequency_coast() -> None:
    frame_count = 90
    offsets = tuple(
        np.pi / 2 if 20 <= frame_index < 45 else 0.0 for frame_index in range(frame_count)
    )
    samples = _capture(
        frame_count=frame_count,
        base_cfo_hz=100_000.0,
        residual_cfo_hz=250.0,
        doppler_rate_hz_s=-1_200.0,
        ambiguity_bits=(0,) * frame_count,
        phase_offsets_rad=offsets,
        noise_sigma=0.005,
    )
    common = {
        "epoch_sample": EPOCH,
        "initial_absolute_cfo_hz": 100_250.0,
        "edge": StarlinkEdge.LOWER,
    }

    legacy = analyze_contiguous_pilot_pnt_kalman(
        samples,
        RATE,
        **common,
        config=PilotPntKalmanConfig(timing_innovation_gate_sigma=100.0),
    )
    corrected = analyze_contiguous_pilot_pnt_kalman_v2(
        samples,
        RATE,
        **common,
        config=PilotPntKalmanConfigV2(timing_innovation_gate_sigma=100.0),
    )

    assert legacy.reacquisition_count == 0
    assert not legacy.frames[-1].phase_update_applied
    assert corrected.reacquisition_count >= 2
    assert corrected.frames[-1].phase_update_applied
    assert corrected.frames[-1].frequency_update_applied
    assert corrected.frames[-1].timing_update_applied
    assert abs(corrected.frames[-1].tracked_doppler_rate_hz_s + 1_200.0) < 50.0

    with pytest.raises(ValueError, match="independent phase reacquisition"):
        analyze_contiguous_pilot_pnt_kalman_v2(
            samples,
            RATE,
            **common,
            config=PilotPntKalmanConfigV2(
                timing_innovation_gate_sigma=100.0,
                independent_phase_reacquisition=False,
            ),
        )
