from __future__ import annotations

import math

import numpy as np
import pytest

from leo.analysis.starlink import (
    PssBankMode,
    PssBankSearchConfig,
    PssEpochCandidate,
    PssSearchOrigin,
    PssSearchTarget,
    PssTrackAssociationConfig,
    associate_pss_timing_tracks,
    compile_pss_projection,
    project_pss_block,
    pss_subband_template,
    search_pss_frame_timing_bank,
)

_CHANNEL_REFERENCE_HZ = 1_824_882_812.5
_EDGE_CENTER_HZ = 1_709_687_500.0


@pytest.mark.parametrize(
    ("sample_rate_hz", "capture_center_hz"),
    (
        (2_500_000, _EDGE_CENTER_HZ),
        (15_000_000, 1_712_500_000.0),
        (20_000_000, 1_715_000_000.0),
        (25_000_000, 1_717_500_000.0),
    ),
)
def test_projection_and_true_cfo_bank_recover_the_same_injected_epoch_at_every_rate(
    sample_rate_hz: int,
    capture_center_hz: float,
) -> None:
    projection = compile_pss_projection(
        input_sample_rate_hz=sample_rate_hz,
        input_center_frequency_hz=capture_center_hz,
        rf_bandwidth_hz=sample_rate_hz,
        target_center_frequency_hz=_EDGE_CENTER_HZ,
        channel_reference_hz=_CHANNEL_REFERENCE_HZ,
    )
    template = pss_subband_template(
        sample_rate_hz,
        slice_center_offset_hz=capture_center_hz - _CHANNEL_REFERENCE_HZ,
    )
    sample_count = round(0.040 * sample_rate_hz)
    epoch_s = 0.00037
    epoch_sample = round(epoch_s * sample_rate_hz)
    frame_period = sample_rate_hz / 750.0
    cfo_hz = -475_000.0
    rng = np.random.default_rng(sample_rate_hz)
    values = np.asarray(
        rng.normal(size=sample_count) + 1j * rng.normal(size=sample_count),
        dtype=np.complex64,
    )
    conditioned = template * np.exp(2j * np.pi * cfo_hz * np.arange(template.size) / sample_rate_hz)
    for frame_index in range(100):
        start = round(epoch_sample + frame_index * frame_period)
        if start + template.size > sample_count:
            break
        values[start : start + template.size] += 25.0 * conditioned

    block = project_pss_block(
        values,
        projection,
        input_device_sample_start=0,
        continuity_segment_index=3,
    )
    result = search_pss_frame_timing_bank(
        block,
        block_index=7,
        bank_config=PssBankSearchConfig(
            coarse_frequency_offsets_hz=(-600_000.0, -500_000.0, -400_000.0),
            fine_frequency_radius_hz=50_000.0,
            fine_frequency_step_hz=25_000.0,
        ),
    )

    assert -475_000.0 in result.searched_frequency_offsets_hz
    best = max(result.modes, key=lambda item: item.candidate.robust_z)
    assert best.origin is PssSearchOrigin.INDEPENDENT_BLIND
    assert min(abs(item.nominal_frequency_offset_hz - cfo_hz) for item in result.modes) <= 25_000.0
    assert best.median_frame_phase_s == pytest.approx(epoch_s, abs=0.6e-6)
    assert best.window_count >= 29
    assert block.input_device_sample_start % projection.decimation_factor == 0
    assert block.input_device_sample_stop % projection.decimation_factor == 0


def test_conditioned_target_filters_phase_and_retains_lineage() -> None:
    sample_rate_hz = 2_500_000
    center_hz = _EDGE_CENTER_HZ
    projection = compile_pss_projection(
        input_sample_rate_hz=sample_rate_hz,
        input_center_frequency_hz=center_hz,
        rf_bandwidth_hz=sample_rate_hz,
        target_center_frequency_hz=center_hz,
        channel_reference_hz=_CHANNEL_REFERENCE_HZ,
    )
    template = pss_subband_template(
        sample_rate_hz,
        slice_center_offset_hz=center_hz - _CHANNEL_REFERENCE_HZ,
    )
    sample_count = 100_000
    values = np.zeros(sample_count, dtype=np.complex64)
    epoch_sample = 800
    for frame_index in range(40):
        start = round(epoch_sample + frame_index * sample_rate_hz / 750.0)
        if start + template.size <= sample_count:
            values[start : start + template.size] += 10.0 * template
    block = project_pss_block(
        values,
        projection,
        input_device_sample_start=0,
        continuity_segment_index=0,
    )
    source_digest = "sha256:" + "1" * 64
    target = PssSearchTarget(
        origin=PssSearchOrigin.GLRT_CONDITIONED,
        frequency_center_hz=0.0,
        frequency_half_width_hz=25_000.0,
        predicted_frame_phase_s=epoch_sample / sample_rate_hz,
        frame_phase_radius_s=2.0e-6,
        source_digest=source_digest,
    )

    result = search_pss_frame_timing_bank(
        block,
        block_index=0,
        target=target,
        bank_config=PssBankSearchConfig(
            coarse_frequency_offsets_hz=(0.0,),
            fine_frequency_radius_hz=0.0,
            fine_frequency_step_hz=25_000.0,
        ),
    )

    assert result.origin is PssSearchOrigin.GLRT_CONDITIONED
    assert result.modes
    assert all(item.source_digest == source_digest for item in result.modes)
    with pytest.raises(ValueError, match="source digest"):
        PssSearchTarget(PssSearchOrigin.GLRT_CONDITIONED)


def test_fine_search_refines_a_near_threshold_coarse_diagnostic() -> None:
    sample_rate_hz = 2_500_000
    center_hz = _EDGE_CENTER_HZ
    projection = compile_pss_projection(
        input_sample_rate_hz=sample_rate_hz,
        input_center_frequency_hz=center_hz,
        rf_bandwidth_hz=sample_rate_hz,
        target_center_frequency_hz=center_hz,
        channel_reference_hz=_CHANNEL_REFERENCE_HZ,
    )
    template = pss_subband_template(
        sample_rate_hz,
        slice_center_offset_hz=center_hz - _CHANNEL_REFERENCE_HZ,
    )
    sample_count = 100_000
    epoch_sample = 925
    true_cfo_hz = -475_000.0
    rng = np.random.default_rng(22)
    values = np.asarray(
        rng.normal(size=sample_count) + 1j * rng.normal(size=sample_count),
        dtype=np.complex64,
    )
    conditioned = template * np.exp(
        2j * np.pi * true_cfo_hz * np.arange(template.size) / sample_rate_hz
    )
    for frame_index in range(40):
        start = round(epoch_sample + frame_index * sample_rate_hz / 750.0)
        if start + template.size <= sample_count:
            values[start : start + template.size] += 1.6 * conditioned
    block = project_pss_block(
        values,
        projection,
        input_device_sample_start=0,
        continuity_segment_index=0,
    )

    result = search_pss_frame_timing_bank(
        block,
        block_index=0,
        bank_config=PssBankSearchConfig(
            coarse_frequency_offsets_hz=(-500_000.0,),
            fine_frequency_radius_hz=50_000.0,
            fine_frequency_step_hz=25_000.0,
        ),
    )

    assert -475_000.0 in result.searched_frequency_offsets_hz
    assert result.no_result_hypothesis_count >= 1
    assert result.modes
    assert all(item.nominal_frequency_offset_hz != -500_000.0 for item in result.modes)
    assert (
        min(abs(item.nominal_frequency_offset_hz - true_cfo_hz) for item in result.modes)
        <= 25_000.0
    )


def test_quadratic_association_rejects_unrelated_phase_modes() -> None:
    period_s = 1.0 / 750.0
    modes: list[PssBankMode] = []
    for block_index, time_s in enumerate(np.linspace(40.0, 49.0, 10)):
        tau = time_s - 44.5
        phase_s = (0.00024 + 3.0e-6 * tau - 0.15e-6 * tau**2) % period_s
        candidate = PssEpochCandidate(
            candidate_index=0,
            epoch_sample=0,
            global_epoch_device_sample=block_index,
            frame_phase_samples=phase_s * 2_500_000,
            frequency_offset_hz=-475_000.0,
            folded_score=2.0,
            folded_median=1.0,
            peak_to_median=2.0,
            robust_z=10.0,
            frame_support=100,
            qualified=True,
        )
        modes.append(
            PssBankMode(
                mode_id=f"signal-{block_index}",
                block_index=block_index,
                continuity_segment_index=0,
                projection_id="projection",
                origin=PssSearchOrigin.INDEPENDENT_BLIND,
                source_digest=None,
                center_time_s=float(time_s),
                nominal_frequency_offset_hz=-475_000.0,
                candidate=candidate,
                median_frame_phase_s=float(phase_s),
                window_count=100,
                strong_window_count=50,
                windows=(),
            )
        )
        distractor_phase = (phase_s + 0.00035 + block_index * 37e-6) % period_s
        modes.append(
            PssBankMode(
                mode_id=f"noise-{block_index}",
                block_index=block_index,
                continuity_segment_index=0,
                projection_id="projection",
                origin=PssSearchOrigin.INDEPENDENT_BLIND,
                source_digest=None,
                center_time_s=float(time_s),
                nominal_frequency_offset_hz=400_000.0,
                candidate=candidate,
                median_frame_phase_s=float(distractor_phase),
                window_count=20,
                strong_window_count=0,
                windows=(),
            )
        )

    tracks = associate_pss_timing_tracks(
        tuple(modes),
        config=PssTrackAssociationConfig(
            minimum_block_count=8,
            minimum_span_s=7.0,
            phase_inlier_radius_s=2.0e-6,
        ),
    )

    assert tracks
    assert tracks[0].mode_ids == tuple(f"signal-{index}" for index in range(10))
    assert tracks[0].rms_residual_s < 1e-12
    assert math.isclose(tracks[0].time_stop_s - tracks[0].time_start_s, 9.0)


def test_projection_rejects_a_target_outside_the_recorded_passband() -> None:
    with pytest.raises(ValueError, match="outside"):
        compile_pss_projection(
            input_sample_rate_hz=15_000_000,
            input_center_frequency_hz=1_000_000_000.0,
            rf_bandwidth_hz=15_000_000,
            target_center_frequency_hz=1_020_000_000.0,
            channel_reference_hz=1_075_117_187.5,
        )
