from __future__ import annotations

import numpy as np
import pytest

from leo.analysis.qam import (
    PilotPntKalmanConfig,
    PilotPntKalmanConfigV2,
    PilotPntKalmanConfigV3,
    PilotPntKalmanSegmentSeed,
    PilotPntKalmanV3Result,
    analyze_contiguous_pilot_pnt_kalman,
    analyze_contiguous_pilot_pnt_kalman_v2,
    analyze_contiguous_pilot_pnt_kalman_v3,
    analyze_piecewise_pilot_pnt_kalman_v3,
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
    epoch_sample: int = EPOCH,
) -> np.ndarray:
    template = qin_edge_pilot_frame(
        RATE,
        StarlinkEdge.LOWER,
        symbol_roll=symbol_roll,
    )
    indexes = np.arange(template.size)
    final_start = epoch_sample + round((frame_count - 1) * RATE / FRAME_RATE_HZ)
    samples = np.zeros(final_start + template.size + 2, dtype=np.complex128)
    offsets = phase_offsets_rad or (0.0,) * frame_count
    if len(offsets) != frame_count:
        raise ValueError("phase-offset fixture must match frame count")
    for frame in range(frame_count):
        start = epoch_sample + round(frame * RATE / FRAME_RATE_HZ)
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


def test_v3_reacquires_full_frame_and_prevents_phase_from_steering_rate() -> None:
    frame_count = 100
    offsets = tuple(0.7 * np.sin(frame_index * 0.15) for frame_index in range(frame_count))
    samples = _capture(
        frame_count=frame_count,
        base_cfo_hz=100_000.0,
        residual_cfo_hz=300.0,
        doppler_rate_hz_s=-1_800.0,
        ambiguity_bits=(0,) * frame_count,
        phase_offsets_rad=offsets,
        noise_sigma=0.01,
    )
    common = {
        "initial_absolute_cfo_hz": 100_300.0,
        "edge": StarlinkEdge.LOWER,
        "maximum_residual_cfo_hz": 2_000.0,
    }
    v2 = analyze_contiguous_pilot_pnt_kalman_v2(
        samples,
        RATE,
        epoch_sample=EPOCH,
        **common,
        config=PilotPntKalmanConfigV2(timing_innovation_gate_sigma=100.0),
    )
    v3 = analyze_contiguous_pilot_pnt_kalman_v3(
        samples,
        RATE,
        # Nearly one full frame away from the true epoch.  V2 would treat
        # this as certain; V3 searches the discrete circular branch first.
        epoch_sample=round(RATE / FRAME_RATE_HZ) - 34,
        **common,
        config=PilotPntKalmanConfigV3(timing_innovation_gate_sigma=100.0),
    )

    assert v3.status is NumericalStatus.COMPLETE
    assert isinstance(v3, PilotPntKalmanV3Result)
    assert v3.frames[0].frame_start_sample == EPOCH
    assert v3.initial_alignment is not None
    assert v3.initial_alignment.epoch_sample == EPOCH
    assert v3.initial_alignment.raw_offset_from_nominal_samples == EPOCH - (
        round(RATE / FRAME_RATE_HZ) - 34
    )
    assert v3.initial_alignment.searched_cfo_count > 1
    assert abs(v2.frames[-1].tracked_doppler_rate_hz_s + 1_800.0) > 400.0
    assert v3.frames[-1].tracked_doppler_rate_hz_s == pytest.approx(-1_800.0, abs=30.0)
    assert v3.phase_update_count >= 95

    with pytest.raises(ValueError, match="phase-safe frequency decoupling"):
        analyze_contiguous_pilot_pnt_kalman_v3(
            samples,
            RATE,
            epoch_sample=EPOCH,
            **common,
            config=PilotPntKalmanConfigV3(
                timing_innovation_gate_sigma=100.0,
                decouple_phase_from_frequency=False,
            ),
        )


def test_v3_tracks_the_last_integer_epoch_before_a_noninteger_frame_period() -> None:
    epoch = int(np.floor(RATE / FRAME_RATE_HZ))
    samples = _capture(
        frame_count=30,
        base_cfo_hz=300.0,
        residual_cfo_hz=0.0,
        doppler_rate_hz_s=0.0,
        ambiguity_bits=(0,) * 30,
        epoch_sample=epoch,
    )

    result = analyze_contiguous_pilot_pnt_kalman_v3(
        samples,
        RATE,
        epoch_sample=0,
        initial_absolute_cfo_hz=300.0,
        edge=StarlinkEdge.LOWER,
        config=PilotPntKalmanConfigV3(timing_innovation_gate_sigma=100.0),
    )

    assert result.status is NumericalStatus.COMPLETE
    assert result.frames[0].frame_start_sample == epoch
    assert result.supported_frame_count == 30
    assert result.timing_update_count >= 28


def test_v3_fails_closed_on_a_noise_only_full_frame_search() -> None:
    generator = np.random.default_rng(0xA11)
    sample_count = round(30 * RATE / FRAME_RATE_HZ)
    samples = (
        generator.normal(size=sample_count) + 1j * generator.normal(size=sample_count)
    ) / np.sqrt(2)

    result = analyze_contiguous_pilot_pnt_kalman_v3(
        samples,
        RATE,
        epoch_sample=0,
        initial_absolute_cfo_hz=0.0,
        edge=StarlinkEdge.LOWER,
    )

    assert result.status is NumericalStatus.NO_RESULT
    assert not result.frames
    assert result.initial_alignment is not None
    assert "no frame passed" in result.reason


def test_v3_rejects_a_search_shifted_rolled_pilot_control() -> None:
    samples = _capture(
        frame_count=20,
        base_cfo_hz=0.0,
        residual_cfo_hz=0.0,
        doppler_rate_hz_s=0.0,
        ambiguity_bits=(0,) * 20,
        symbol_roll=CONTROL_SYMBOL_ROLL,
    )

    result = analyze_contiguous_pilot_pnt_kalman_v3(
        samples,
        RATE,
        epoch_sample=0,
        initial_absolute_cfo_hz=0.0,
        edge=StarlinkEdge.LOWER,
    )

    assert result.status is NumericalStatus.NO_RESULT
    assert result.initial_alignment is not None
    assert result.initial_alignment.expected_symbol_roll == 0
    assert result.initial_alignment.control_score is not None
    assert result.initial_alignment.exact_score is not None
    assert result.initial_alignment.control_score > result.initial_alignment.exact_score
    assert not result.frames


def test_v3_rolled_control_replay_rejects_the_exact_pilot() -> None:
    samples = _capture(
        frame_count=20,
        base_cfo_hz=0.0,
        residual_cfo_hz=0.0,
        doppler_rate_hz_s=0.0,
        ambiguity_bits=(0,) * 20,
    )

    result = analyze_contiguous_pilot_pnt_kalman_v3(
        samples,
        RATE,
        epoch_sample=0,
        initial_absolute_cfo_hz=0.0,
        edge=StarlinkEdge.LOWER,
        expected_symbol_roll=CONTROL_SYMBOL_ROLL,
    )

    assert result.status is NumericalStatus.NO_RESULT
    assert result.initial_alignment is not None
    assert result.initial_alignment.expected_symbol_roll == CONTROL_SYMBOL_ROLL
    assert result.initial_alignment.control_score is not None
    assert result.initial_alignment.exact_score is not None
    assert result.initial_alignment.control_score > result.initial_alignment.exact_score
    assert not result.frames


@pytest.mark.parametrize("initial_cfo_hz", (750.0, 1_500.0))
def test_v3_jointly_refines_epoch_when_nominal_cfo_hits_frame_null(
    initial_cfo_hz: float,
) -> None:
    samples = _capture(
        frame_count=15,
        base_cfo_hz=0.0,
        residual_cfo_hz=0.0,
        doppler_rate_hz_s=0.0,
        ambiguity_bits=(0,) * 15,
    )

    result = analyze_contiguous_pilot_pnt_kalman_v3(
        samples,
        RATE,
        epoch_sample=0,
        initial_absolute_cfo_hz=initial_cfo_hz,
        maximum_residual_cfo_hz=2_000.0,
        edge=StarlinkEdge.LOWER,
    )

    assert result.status is NumericalStatus.COMPLETE
    assert result.frames[0].frame_start_sample == EPOCH
    assert result.supported_frame_count == 15
    assert result.frames[-1].tracked_absolute_cfo_hz == pytest.approx(0.0, abs=1.0)


def test_v3_policy_flags_require_actual_booleans() -> None:
    with pytest.raises(ValueError, match="policy flags must be boolean"):
        PilotPntKalmanConfigV3(decouple_phase_from_frequency=1)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("field", "message"),
    (
        ("independent_phase_reacquisition", "independent phase reacquisition"),
        ("initial_full_frame_epoch_acquisition", "initial full-frame epoch acquisition"),
        ("decouple_phase_from_frequency", "phase-safe frequency decoupling"),
    ),
)
def test_piecewise_v3_enforces_required_policies(field: str, message: str) -> None:
    samples = _capture(
        frame_count=20,
        base_cfo_hz=0.0,
        residual_cfo_hz=0.0,
        doppler_rate_hz_s=0.0,
        ambiguity_bits=(0,) * 20,
    )
    config_values = {field: False}

    with pytest.raises(ValueError, match=message):
        analyze_piecewise_pilot_pnt_kalman_v3(
            samples,
            RATE,
            segments=(PilotPntKalmanSegmentSeed(0, len(samples), 0, 0.0),),
            edge=StarlinkEdge.LOWER,
            config=PilotPntKalmanConfigV3(**config_values),  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    ("maximum_residual_cfo_hz", "message"),
    (
        (0.0, "finite and positive"),
        (0.5 / 4.4e-6 + 1.0, "Nyquist"),
    ),
)
def test_v3_rejects_invalid_cfo_bounds_before_data_dependent_outcomes(
    maximum_residual_cfo_hz: float,
    message: str,
) -> None:
    samples = np.zeros(4_000, dtype=np.complex128)
    with pytest.raises(ValueError, match=message):
        analyze_contiguous_pilot_pnt_kalman_v3(
            samples,
            RATE,
            epoch_sample=0,
            initial_absolute_cfo_hz=0.0,
            maximum_residual_cfo_hz=maximum_residual_cfo_hz,
            edge=StarlinkEdge.LOWER,
        )
    with pytest.raises(ValueError, match=message):
        analyze_piecewise_pilot_pnt_kalman_v3(
            samples,
            RATE,
            segments=(PilotPntKalmanSegmentSeed(0, len(samples), 0, 0.0),),
            maximum_residual_cfo_hz=maximum_residual_cfo_hz,
            edge=StarlinkEdge.LOWER,
        )


def test_piecewise_v3_preserves_an_insufficient_segment_outcome() -> None:
    samples = np.ones(4_000, dtype=np.complex128)
    result = analyze_piecewise_pilot_pnt_kalman_v3(
        samples,
        RATE,
        segments=(PilotPntKalmanSegmentSeed(0, len(samples), 0, 0.0),),
        edge=StarlinkEdge.LOWER,
    )

    assert result.status is NumericalStatus.INSUFFICIENT
    assert result.complete_segment_count == 0
    assert result.segments[0].alignment.status is NumericalStatus.INSUFFICIENT
    assert result.segments[0].tracking.status is NumericalStatus.INSUFFICIENT
    assert "sufficient tracking data" in result.reason


def test_piecewise_v3_reacquires_after_a_confirmed_full_epoch_and_cfo_jump() -> None:
    period = RATE / FRAME_RATE_HZ
    boundary = EPOCH + round(20 * period)
    second_epoch = 1_000
    template = qin_edge_pilot_frame(RATE, StarlinkEdge.LOWER)
    indexes = np.arange(template.size)
    final_start = boundary + second_epoch + round(19 * period)
    samples = np.zeros(final_start + template.size + 2, dtype=np.complex128)

    for frame in range(20):
        start = EPOCH + round(frame * period)
        absolute = start + indexes
        samples[absolute] += template * np.exp(2j * np.pi * 300.0 * absolute / RATE)
    for frame in range(20):
        start = boundary + second_epoch + round(frame * period)
        absolute = start + indexes
        samples[absolute] += template * np.exp(2j * np.pi * 900.0 * absolute / RATE)

    result = analyze_piecewise_pilot_pnt_kalman_v3(
        samples,
        RATE,
        segments=(
            PilotPntKalmanSegmentSeed(0, boundary, 0, 300.0),
            PilotPntKalmanSegmentSeed(boundary, len(samples), 0, 900.0),
        ),
        edge=StarlinkEdge.LOWER,
    )

    assert result.status is NumericalStatus.COMPLETE
    assert result.complete_segment_count == 2
    assert result.reacquisition_count == 1
    first, second = result.segments
    assert first.alignment.epoch_sample == EPOCH
    assert second.alignment.epoch_sample == second_epoch
    assert first.tracking.supported_frame_count == 20
    assert second.tracking.supported_frame_count == 20
    assert abs(first.tracking.frames[-1].tracked_doppler_rate_hz_s) < 1.0
    assert abs(second.tracking.frames[-1].tracked_doppler_rate_hz_s) < 1.0
