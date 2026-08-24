from __future__ import annotations

from dataclasses import replace

import numpy as np

from leo.analysis.starlink.dwell_doppler import (
    DwellDopplerConfig,
    DwellDopplerStatus,
    DwellDopplerTrackInput,
    FrameCfoMeasurement,
    GlrtProbe,
    batch_joined_ramps,
    independent_probe_fits,
    infer_track_doppler,
)
from leo.analysis.starlink.templates import StarlinkEdge


def _synthetic_track_and_frames() -> tuple[DwellDopplerTrackInput, tuple[FrameCfoMeasurement, ...]]:
    probes = []
    frames = []
    local_rate = -3_800.0
    probe_index = 0
    for ramp_index in range(12):
        ramp_start = 1.0 + 0.12 * ramp_index
        ramp_center = ramp_start + 0.034
        ramp_intercept = 90_000.0 - 720.0 * ramp_index
        for within_ramp in range(3):
            probe_time = ramp_start + 0.025 * within_ramp
            probes.append(
                GlrtProbe(
                    probe_index=probe_index,
                    detection_time_s=probe_time,
                    detection_sample_start=round(probe_time * 2_500_000),
                    local_epoch_sample=500,
                    source_cfo_hz=100_000.0 - 6_000.0 * probe_time,
                    exact_score=0.7,
                    control_score=0.04,
                    margin=0.66,
                )
            )
            for frame_index in range(15):
                time_s = probe_time + 0.0007 + frame_index / 750.0
                noise = 3.0 * np.sin(0.7 * len(frames))
                cfo = ramp_intercept + local_rate * (time_s - ramp_center) + noise
                frames.append(
                    FrameCfoMeasurement(
                        row_index=len(frames),
                        probe_index=probe_index,
                        time_s=time_s,
                        train_cfo_hz=float(cfo),
                        validation_cfo_hz=float(cfo + 2.0 * np.cos(len(frames))),
                        train_exact_score=0.75,
                        train_control_score=0.04,
                        residual_grid_edge=False,
                    )
                )
            probe_index += 1
    track = DwellDopplerTrackInput(
        branch_id="branch",
        stream_id="stream-0",
        receiver_id=0,
        edge=StarlinkEdge.LOWER,
        start_s=1.0,
        end_s=2.37,
        reference_time_s=1.0,
        glrt_coefficients_hz=(-6_000.0, 100_000.0),
        glrt_rate_sigma_hz_s=50.0,
        probe_samples=50_000,
        probes=tuple(probes),
    )
    return track, tuple(frames)


def test_batch_ramps_recover_frequency_continuous_groups() -> None:
    track, frames = _synthetic_track_and_frames()
    config = DwellDopplerConfig(bootstrap_replicates=200)

    locks = independent_probe_fits(frames, config)
    ramps = batch_joined_ramps(frames, locks, config)

    assert len(locks) == len(track.probes)
    assert len(ramps) >= 10
    assert all(ramp.span_s >= config.minimum_ramp_span_s for ramp in ramps)


def test_inference_recovers_local_rate_and_rejects_reset_biased_glrt() -> None:
    track, frames = _synthetic_track_and_frames()
    config = DwellDopplerConfig(bootstrap_replicates=500)

    result = infer_track_doppler(track, frames, config)

    assert result.status is DwellDopplerStatus.COMPLETE
    assert np.isclose(
        result.diagnostics["overall_glrt_rate_hz_s"],
        -6_000.0,
    )
    assert np.isclose(
        result.diagnostics["local_corrected_rate_hz_s"],
        -3_800.0,
        atol=30.0,
    )
    assert result.diagnostics["odd_validation_reduction_percent"] > 20.0


def test_inference_fails_closed_without_glrt_support() -> None:
    track, frames = _synthetic_track_and_frames()
    weak = replace(track, probes=track.probes[:3])

    result = infer_track_doppler(
        weak,
        frames,
        DwellDopplerConfig(bootstrap_replicates=200),
    )

    assert result.status is DwellDopplerStatus.INSUFFICIENT_GLRT_SUPPORT
    assert "local_corrected_rate_hz_s" not in result.diagnostics
