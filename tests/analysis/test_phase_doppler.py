from __future__ import annotations

import numpy as np

from leo.analysis.starlink.phase_doppler import (
    CarrierFrameObservation,
    estimate_frame_carrier_observations,
    fit_constant_rate_phase_doppler,
)


def _observation(time_s: float, phase: float, frequency: float, container: int):
    return CarrierFrameObservation(
        time_s=time_s,
        phase_cycles=phase,
        doppler_hz=frequency,
        coherence=0.9,
        mean_normalized_power=0.4,
        control_phase_cycles=0.0,
        control_doppler_hz=frequency + 700.0,
        control_coherence=0.1,
        container_id=container,
    )


def test_constant_rate_tracker_recovers_linear_doppler_and_continuous_phase() -> None:
    reference = 0.5
    frequency = 12_000.0
    rate = -5_800.0
    times = np.arange(0.0, 1.0, 1.0 / 750.0)
    phase = 0.17 + frequency * (times - reference) + 0.5 * rate * (times - reference) ** 2
    observations = tuple(
        _observation(time, value % 1.0, frequency + rate * (time - reference), int(time / 0.02))
        for time, value in zip(times, phase, strict=True)
    )

    result = fit_constant_rate_phase_doppler(observations)

    assert abs(result.doppler_fit.slope_hz_per_s - rate) < 1e-6
    assert abs(result.doppler_fit.intercept_at_reference_hz - frequency) < 10.0
    assert max(abs(item.innovation_cycles) for item in result.transitions) < 1e-8
    assert all(item.accepted_continuity for item in result.transitions)


def test_phase_reference_jump_is_explicit_and_does_not_bend_doppler() -> None:
    rate = -6_000.0
    times = np.arange(0.0, 0.20, 1.0 / 750.0)
    frequency = 40_000.0 + rate * times
    phase = 0.1 + 40_000.0 * times + 0.5 * rate * times**2
    phase[times >= 0.10] += 0.25
    observations = tuple(
        _observation(time, value % 1.0, measured, int(time / 0.02))
        for time, value, measured in zip(times, phase, frequency, strict=True)
    )

    result = fit_constant_rate_phase_doppler(observations, phase_gate_cycles=0.10)

    slips = [item for item in result.transitions if not item.accepted_continuity]
    assert len(slips) == 1
    assert abs(abs(slips[0].innovation_cycles) - 0.25) < 1e-8
    assert slips[0].eighth_cycle_error < 1e-8
    assert abs(result.doppler_fit.slope_hz_per_s - rate) < 1e-6


def test_frame_discriminator_restores_local_nco_phase_and_residual_frequency() -> None:
    symbols = 64
    frames = 3
    times = np.arange(symbols, dtype=float) * 4.4e-6
    times = times[None, :] + np.arange(frames)[:, None] / 750.0
    nco = -150_000.0
    residual = 225.0
    raw_phase = 0.21 + (nco + residual) * times
    local_values = np.exp(2j * np.pi * (raw_phase - nco * times))
    control = np.exp(2j * np.pi * (0.37 * np.arange(symbols)[None, :] + 0.1))
    power = np.full(local_values.shape, 0.5)

    result = estimate_frame_carrier_observations(
        local_values,
        np.broadcast_to(control, local_values.shape),
        power,
        power,
        times,
        nco_frequency_hz=nco,
        absolute_time_offset_s=12.0,
        container_id=7,
        residual_frequency_span_hz=500.0,
        residual_frequency_step_hz=25.0,
    )

    assert len(result) == frames
    assert all(abs(item.doppler_hz - (nco + residual)) < 1e-9 for item in result)
    expected = (0.21 + (nco + residual) * times.mean(axis=1) + 0.5) % 1.0 - 0.5
    assert np.allclose([item.phase_cycles for item in result], expected, atol=1e-10)
    assert all(item.coherence > 0.999 for item in result)
    assert all(item.control_coherence < 0.2 for item in result)
