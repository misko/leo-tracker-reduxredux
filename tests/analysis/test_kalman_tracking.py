from __future__ import annotations

import math

import numpy as np
import pytest

from leo.analysis.starlink.kalman_tracking import (
    KalmanFrameObservation,
    PolynomialFrequencyModel,
    extract_probe_frame_measurements,
    process_covariance,
    state_transition,
    track_frame_observations,
)
from leo.analysis.starlink.templates import FRAME_RATE_HZ, StarlinkEdge, qin_edge_pilot_frame
from leo.contracts.kalman_tracking import KalmanTrackingConfigV1


def test_paper_transition_and_continuous_noise_discretization_are_exact() -> None:
    dt = 0.2
    transition = state_transition(dt)
    covariance = process_covariance(
        dt,
        carrier_acceleration_psd_rad2_s3=4.0,
        frame_rate_psd_s2_s=9.0,
    )

    np.testing.assert_allclose(
        transition,
        (
            (1, dt, 0.5 * dt**2, 0, 0),
            (0, 1, dt, 0, 0),
            (0, 0, 1, 0, 0),
            (0, 0, 0, 1, dt),
            (0, 0, 0, 0, 1),
        ),
    )
    np.testing.assert_allclose(
        covariance[:3, :3],
        4
        * np.asarray(
            (
                (dt**5 / 20, dt**4 / 8, dt**3 / 6),
                (dt**4 / 8, dt**3 / 3, dt**2 / 2),
                (dt**3 / 6, dt**2 / 2, dt),
            )
        ),
    )
    np.testing.assert_allclose(
        covariance[3:, 3:],
        9 * np.asarray(((dt**3 / 3, dt**2 / 2), (dt**2 / 2, dt))),
    )
    assert np.count_nonzero(covariance[:3, 3:]) == 0
    assert np.count_nonzero(covariance[3:, :3]) == 0


def test_five_state_filter_tracks_wrapped_phase_frames_doppler_and_rate_across_gap() -> None:
    frame_period = 1 / FRAME_RATE_HZ
    phase0 = 0.4
    doppler0_hz = 1_200.0
    doppler_rate_hz_s = 25.0
    frame_rate_error = 2e-7
    observations = []
    for frame_index in (*range(400), *range(410, 800)):
        time_s = frame_index * frame_period
        phase = phase0 + 2 * math.pi * (doppler0_hz * time_s + 0.5 * doppler_rate_hz_s * time_s**2)
        observations.append(
            KalmanFrameObservation(
                frame_index=frame_index,
                sample_start=frame_index * 10,
                time_s=time_s + 1e-4,
                prompt_coherence=1.0,
                carrier_phase_rad=_wrap(phase),
                doppler_hz=doppler0_hz + doppler_rate_hz_s * time_s,
                frame_phase_s=frame_rate_error * time_s,
            )
        )

    estimates = track_frame_observations(
        tuple(observations),
        KalmanTrackingConfigV1(),
        initial_doppler_rate_hz_s=doppler_rate_hz_s,
    )

    assert len(estimates) == 790
    assert estimates[-1].doppler_shift_hz == pytest.approx(
        doppler0_hz + doppler_rate_hz_s * 799 * frame_period,
        abs=1e-6,
    )
    assert estimates[-1].doppler_rate_hz_s == pytest.approx(doppler_rate_hz_s, abs=1e-5)
    assert estimates[-1].frame_rate_error_s_s == pytest.approx(frame_rate_error, abs=1e-10)
    assert max(abs(item.phase_innovation_rad) for item in estimates) < 1e-6


def test_filter_flags_phase_slip_and_abrupt_cfo_correction() -> None:
    config = KalmanTrackingConfigV1(
        carrier_phase_measurement_sigma_rad=0.02,
        carrier_frequency_measurement_sigma_rad_s=2 * math.pi,
    )
    observations = []
    phase = 0.0
    previous_time = 0.0
    for frame_index in range(1_000):
        time_s = frame_index / FRAME_RATE_HZ
        frequency_hz = 1_000.0 + (180.0 if time_s >= 0.8 else 0.0)
        phase += 2 * math.pi * frequency_hz * (time_s - previous_time)
        measured_phase = phase + (math.pi / 2 if frame_index == 450 else 0.0)
        observations.append(
            KalmanFrameObservation(
                frame_index,
                frame_index,
                time_s,
                1.0,
                _wrap(measured_phase),
                frequency_hz,
                0.0,
            )
        )
        previous_time = time_s

    estimates = track_frame_observations(tuple(observations), config, initial_doppler_rate_hz_s=0.0)

    assert any(item.phase_slip_detected for item in estimates)
    corrections = [item for item in estimates if item.cfo_correction_detected]
    assert corrections
    assert corrections[0].observation.time_s == pytest.approx(0.8, abs=1 / FRAME_RATE_HZ)
    assert corrections[0].estimated_cfo_correction_hz is not None
    assert corrections[0].estimated_cfo_correction_hz > 75


def test_known_pilot_frame_measurements_recover_phase_and_linear_doppler() -> None:
    sample_rate_hz = 2_500_000
    probe_samples = 50_000
    epoch_sample = 100
    model = PolynomialFrequencyModel(0.0, (20.0, 1_500.0))
    template = np.asarray(
        qin_edge_pilot_frame(sample_rate_hz, StarlinkEdge.LOWER), dtype=np.complex128
    )
    samples = np.zeros(probe_samples, dtype=np.complex128)
    frame_number = 0
    while True:
        frame_start = epoch_sample + round(frame_number * sample_rate_hz / FRAME_RATE_HZ)
        if frame_start + len(template) > len(samples):
            break
        indexes = np.arange(frame_start, frame_start + len(template))
        samples[indexes] += template * np.exp(1j * model.phase_rad(indexes / sample_rate_hz))
        frame_number += 1

    measured = extract_probe_frame_measurements(
        samples,
        probe_sample_start=0,
        local_epoch_sample=epoch_sample,
        sample_rate_hz=sample_rate_hz,
        model=model,
        edge=StarlinkEdge.LOWER,
        pilot_symbol_count=64,
        start_time_s=0.0,
        end_time_s=1.0,
    )

    assert len(measured) == frame_number
    assert min(item.prompt_coherence for item in measured) > 0.999999
    for item in measured:
        assert item.doppler_hz == pytest.approx(float(model.frequency_hz(item.time_s)), abs=1e-8)
        assert _wrap(item.carrier_phase_rad - float(model.phase_rad(item.time_s))) == pytest.approx(
            0.0, abs=1e-8
        )


def _wrap(value: float) -> float:
    return (value + math.pi) % (2 * math.pi) - math.pi
