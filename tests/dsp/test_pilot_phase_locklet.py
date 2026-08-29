from __future__ import annotations

import math

import numpy as np
import pytest

from leo.analysis.qam import PilotPhaseLockletConfig, analyze_contiguous_pilot_phase_locklet
from leo.analysis.starlink import NumericalStatus, qin_edge_pilot_frame
from leo.analysis.starlink.templates import CONTROL_SYMBOL_ROLL, FRAME_RATE_HZ
from leo.contracts.states import StarlinkEdge

EPOCH = 37


def _capture(
    sample_rate_hz: float,
    *,
    frame_count: int = 60,
    base_cfo_hz: float = 100_000.0,
    residual_cfo_hz: float = 260.0,
    doppler_rate_hz_s: float = -1_400.0,
    phase_bias_hz: float = -136.0,
    held_out_offsets_rad: tuple[float, ...] | None = None,
    missing_frames: tuple[int, ...] = (),
    symbol_roll: int = 0,
    noise_sigma: float = 0.002,
) -> np.ndarray:
    template = qin_edge_pilot_frame(
        sample_rate_hz,
        StarlinkEdge.LOWER,
        symbol_roll=symbol_roll,
    )
    indexes = np.arange(template.size, dtype=float)
    integer_indexes = indexes.astype(int)
    final_start = EPOCH + round((frame_count - 1) * sample_rate_hz / FRAME_RATE_HZ)
    samples = np.zeros(final_start + template.size + 2, dtype=np.complex128)
    held_out = held_out_offsets_rad or (0.0,) * frame_count
    if len(held_out) != frame_count:
        raise ValueError("held-out phase fixture must match frame count")
    for frame_index in range(frame_count):
        if frame_index in missing_frames:
            continue
        start = EPOCH + round(frame_index * sample_rate_hz / FRAME_RATE_HZ)
        time_s = (start + indexes) / sample_rate_hz
        # The frame-constant term is deliberately absent from the intraframe
        # phase slope.  It reproduces the observed modulo-375 Hz nuisance
        # between the two otherwise coherent carrier observables.
        frame_bias_rad = 2 * math.pi * phase_bias_hz * frame_index / FRAME_RATE_HZ
        ambiguity_rad = math.pi * ((frame_index // 3 + frame_index // 11) % 2)
        phase = (
            0.4
            + ambiguity_rad
            + frame_bias_rad
            + held_out[frame_index]
            + 2
            * math.pi
            * ((base_cfo_hz + residual_cfo_hz) * time_s + 0.5 * doppler_rate_hz_s * time_s**2)
        )
        samples[start + integer_indexes] += template * np.exp(1j * phase)
    if noise_sigma:
        generator = np.random.default_rng(0xB1A5)
        samples += (
            noise_sigma
            * (generator.normal(size=samples.size) + 1j * generator.normal(size=samples.size))
            / np.sqrt(2)
        )
    return samples


def _wrapped_hz_error(actual_hz: float, expected_hz: float) -> float:
    period_hz = FRAME_RATE_HZ / 2
    return (actual_hz - expected_hz + period_hz / 2) % period_hz - period_hz / 2


@pytest.mark.parametrize(
    "sample_rate_hz",
    [2_500_000.0, 3_000_000.0, 5_000_000.0, 10_000_000.0, 15_000_000.0, 20_000_000.0],
)
def test_prefix_trained_bias_qualifies_only_held_out_phase(sample_rate_hz: float) -> None:
    samples = _capture(sample_rate_hz)

    result = analyze_contiguous_pilot_phase_locklet(
        samples,
        sample_rate_hz,
        epoch_sample=EPOCH,
        initial_absolute_cfo_hz=100_260.0,
        edge=StarlinkEdge.LOWER,
    )

    assert result.status is NumericalStatus.COMPLETE
    assert result.phase_trackability_qualified
    assert result.phase_bias_hz_modulo is not None
    assert _wrapped_hz_error(result.phase_bias_hz_modulo, -136.0) == pytest.approx(0, abs=1.0)
    assert result.training_interval_count == 12
    assert result.held_out_interval_count >= 40
    assert result.held_out_gate_pass_count == result.held_out_interval_count
    assert result.held_out_phase_rms_rad is not None
    assert result.held_out_phase_rms_rad < 0.01
    assert result.training_phase_rms_rad is not None
    assert result.training_phase_rms_rad < 0.01
    assert result.training_circular_concentration is not None
    assert result.training_circular_concentration > 0.99
    assert sum(item.training for item in result.intervals) == result.training_interval_count
    assert sum(item.held_out for item in result.intervals) == result.held_out_interval_count
    assert all(
        item.centered_innovation_modulo_pi_rad is not None and not item.gate_passed
        for item in result.intervals
        if item.training
    )
    assert not result.absolute_carrier_phase_resolved
    assert result.phase_does_not_update_cfo_or_rate
    assert result.training_excluded_from_held_out_scoring
    assert not result.held_out_used_for_nuisance_fit
    assert result.adjacent_one_step_innovations
    assert result.held_out_gate_does_not_control_future_reference
    assert result.known_symbols_only
    assert result.candidate_only


@pytest.mark.parametrize("phase_bias_hz", [-511.0, -136.0, 239.0])
def test_phase_bias_is_invariant_to_the_modulo_375_hz_alias(phase_bias_hz: float) -> None:
    common = {
        "sample_rate_hz": 2_500_000.0,
        "epoch_sample": EPOCH,
        "initial_absolute_cfo_hz": 100_260.0,
        "edge": StarlinkEdge.LOWER,
    }
    first = analyze_contiguous_pilot_phase_locklet(
        _capture(2_500_000.0, phase_bias_hz=phase_bias_hz),
        **common,
    )
    aliased = analyze_contiguous_pilot_phase_locklet(
        _capture(2_500_000.0, phase_bias_hz=phase_bias_hz + FRAME_RATE_HZ / 2),
        **common,
    )

    assert first.phase_bias_hz_modulo == pytest.approx(aliased.phase_bias_hz_modulo, abs=0.2)
    assert first.held_out_phase_rms_rad == pytest.approx(
        aliased.held_out_phase_rms_rad,
        abs=5e-5,
    )


def test_training_prefix_cannot_hide_a_held_out_phase_failure() -> None:
    frame_count = 60
    generator = np.random.default_rng(0xC0FFEE)
    offsets = tuple(
        0.0 if frame_index <= 12 else float(generator.uniform(-math.pi / 2, math.pi / 2))
        for frame_index in range(frame_count)
    )
    clean = analyze_contiguous_pilot_phase_locklet(
        _capture(2_500_000.0, frame_count=frame_count, noise_sigma=0.0),
        2_500_000.0,
        epoch_sample=EPOCH,
        initial_absolute_cfo_hz=100_260.0,
        edge=StarlinkEdge.LOWER,
    )
    poisoned = analyze_contiguous_pilot_phase_locklet(
        _capture(
            2_500_000.0,
            frame_count=frame_count,
            held_out_offsets_rad=offsets,
            noise_sigma=0.0,
        ),
        2_500_000.0,
        epoch_sample=EPOCH,
        initial_absolute_cfo_hz=100_260.0,
        edge=StarlinkEdge.LOWER,
    )

    assert clean.status is poisoned.status is NumericalStatus.COMPLETE
    assert clean.training_interval_count == poisoned.training_interval_count == 12
    assert clean.phase_bias_hz_modulo == poisoned.phase_bias_hz_modulo
    assert clean.training_phase_rms_rad == poisoned.training_phase_rms_rad
    assert clean.training_circular_concentration == poisoned.training_circular_concentration
    assert tuple(item for item in clean.intervals if item.training) == tuple(
        item for item in poisoned.intervals if item.training
    )
    np.testing.assert_allclose(
        [item.absolute_cfo_measurement_hz for item in clean.frames],
        [item.absolute_cfo_measurement_hz for item in poisoned.frames],
        rtol=0,
        atol=1e-8,
    )
    assert clean.phase_trackability_qualified
    assert not poisoned.phase_trackability_qualified
    assert poisoned.held_out_phase_rms_rad is not None
    assert poisoned.held_out_phase_rms_rad > 0.5
    assert "held-out" in poisoned.phase_trackability_reason


def test_fixed_training_prefix_never_recruits_later_good_frames() -> None:
    result = analyze_contiguous_pilot_phase_locklet(
        _capture(2_500_000.0, frame_count=60, missing_frames=(4,), noise_sigma=0.0),
        2_500_000.0,
        epoch_sample=EPOCH,
        initial_absolute_cfo_hz=100_260.0,
        edge=StarlinkEdge.LOWER,
    )

    assert result.status is NumericalStatus.INSUFFICIENT
    assert result.supported_frame_count == 59
    assert result.training_interval_count == 0
    assert not result.phase_trackability_qualified
    assert "fixed training prefix" in result.phase_trackability_reason


def test_positive_alias_boundary_canonicalizes_to_negative_half_period() -> None:
    result = analyze_contiguous_pilot_phase_locklet(
        _capture(
            2_500_000.0,
            phase_bias_hz=FRAME_RATE_HZ / 4,
            noise_sigma=0.0,
        ),
        2_500_000.0,
        epoch_sample=EPOCH,
        initial_absolute_cfo_hz=100_260.0,
        edge=StarlinkEdge.LOWER,
    )

    assert result.phase_bias_hz_modulo is not None
    assert result.phase_bias_hz_modulo < 0
    assert result.phase_bias_hz_modulo == pytest.approx(-FRAME_RATE_HZ / 4, abs=0.5)


def test_rolled_control_and_short_or_zero_windows_fail_closed() -> None:
    rolled = analyze_contiguous_pilot_phase_locklet(
        _capture(2_500_000.0, symbol_roll=CONTROL_SYMBOL_ROLL),
        2_500_000.0,
        epoch_sample=EPOCH,
        initial_absolute_cfo_hz=100_260.0,
        edge=StarlinkEdge.LOWER,
    )
    short = analyze_contiguous_pilot_phase_locklet(
        _capture(2_500_000.0, frame_count=10),
        2_500_000.0,
        epoch_sample=EPOCH,
        initial_absolute_cfo_hz=100_260.0,
        edge=StarlinkEdge.LOWER,
    )
    zero = analyze_contiguous_pilot_phase_locklet(
        np.zeros(round(2_500_000 / FRAME_RATE_HZ), dtype=np.complex128),
        2_500_000.0,
        epoch_sample=0,
        initial_absolute_cfo_hz=0.0,
        edge=StarlinkEdge.LOWER,
    )

    assert rolled.status is NumericalStatus.INSUFFICIENT
    assert not rolled.phase_trackability_qualified
    assert short.status is NumericalStatus.INSUFFICIENT
    assert not short.phase_trackability_qualified
    assert zero.status is NumericalStatus.NO_RESULT
    assert not zero.phase_trackability_qualified
    assert zero.complete_frame_count > 0


def test_configuration_rejects_unbounded_or_ambiguous_policy() -> None:
    with pytest.raises(ValueError, match="pi/2"):
        PilotPhaseLockletConfig(phase_innovation_gate_rad=2.0)
    with pytest.raises(ValueError, match="odd"):
        PilotPhaseLockletConfig(fractional_timing_grid_points=100)
    with pytest.raises(ValueError, match="prefix"):
        PilotPhaseLockletConfig(training_interval_count=2)
