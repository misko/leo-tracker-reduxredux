from __future__ import annotations

import json
import math
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pytest

from leo.analysis.controls import (
    ControlConfig,
    ControlResult,
    build_scientific_summary,
    evaluate_candidate_controls,
)
from leo.analysis.doppler import (
    DopplerFitConfig,
    LockedFrame,
    LockedIntegrationConfig,
    MotionClass,
    TleAssociationResult,
    TleAssociationStatus,
    TlePrediction,
    associate_tle_candidate,
    dedoppler_locked_integration,
    fit_doppler,
)
from leo.analysis.starlink import (
    NumericalStatus,
    ReceiverFrequencyCalibration,
    qin_edge_pilot_frame,
)
from leo.analysis.starlink.long_dwell import (
    ActivityTrackingConfig,
    ActivityTrackingResult,
    CandidateCloudConfig,
    CandidateCloudResult,
    CandidateTrack,
    CloudCandidate,
    DenseRefinementConfig,
    DenseRefinementWindow,
    QamHandoffResult,
    RefinedCandidate,
    ScientificConfidence,
    SparseSurveyConfig,
    SparseSurveyCoverage,
    SparseSurveyResult,
    SurveyCandidate,
    build_candidate_cloud,
    dense_refine_candidates,
    qam_handoff,
    sparse_whole_dwell_survey,
    track_candidate_activity,
    validate_raw_iq,
)
from leo.analysis.waterfall import WaterfallConfig, bounded_waterfall
from leo.contracts.radio import IqBlockMetadataV1, NanosecondIntervalV1
from leo.contracts.states import StarlinkEdge
from leo.domain.iq import IqBlock

RATE = 2_500_000


class _SegmentedReader:
    def __init__(
        self,
        segments: tuple[tuple[int, np.ndarray], ...],
        *,
        sample_count: int,
        sample_rate_hz: int = RATE,
    ) -> None:
        self._segments = tuple(
            (start, np.ascontiguousarray(values, dtype="<i2")) for start, values in segments
        )
        self._sample_count = sample_count
        self._sample_rate_hz = sample_rate_hz
        self.requested_block_samples: list[int] = []
        self.maximum_yielded_samples = 0

    @property
    def sample_rate_hz(self) -> int:
        return self._sample_rate_hz

    @property
    def sample_count(self) -> int:
        return self._sample_count

    @property
    def receiver_ids(self) -> tuple[int, ...]:
        return tuple(range(self._segments[0][1].shape[1]))

    def iter_blocks(self, *, block_samples: int) -> Iterator[IqBlock]:
        self.requested_block_samples.append(block_samples)
        interval = NanosecondIntervalV1(lower_ns=0, upper_ns=0)
        for segment_start, segment in self._segments:
            for offset in range(0, len(segment), block_samples):
                values = segment[offset : offset + block_samples]
                self.maximum_yielded_samples = max(self.maximum_yielded_samples, len(values))
                yield IqBlock(
                    samples=values,
                    metadata=IqBlockMetadataV1(
                        radio_id="synthetic",
                        receiver_ids=self.receiver_ids,
                        sample_count=len(values),
                        session_sample_start=segment_start + offset,
                        host_request_utc_ns=interval,
                        host_request_monotonic_ns=interval,
                    ),
                )


def _reader(values: np.ndarray, *, sample_count: int | None = None) -> _SegmentedReader:
    return _SegmentedReader(
        ((0, values),),
        sample_count=len(values) if sample_count is None else sample_count,
    )


def _pilot_window(
    *,
    epoch: int,
    absolute_cfo_hz: float,
    sample_count: int = 14_000,
    seed: int = 1,
) -> np.ndarray:
    rng = np.random.default_rng(seed)
    values = rng.normal(0, 0.01 / np.sqrt(2), sample_count) + 1j * rng.normal(
        0, 0.01 / np.sqrt(2), sample_count
    )
    template = qin_edge_pilot_frame(RATE, StarlinkEdge.LOWER)
    indexes = np.arange(template.size)
    frame = 0
    while True:
        start = epoch + round(frame * RATE / 750.0)
        if start + template.size > sample_count:
            break
        values[start + indexes] += (
            0.25 * np.exp(2j * np.pi * absolute_cfo_hz * (start + indexes) / RATE) * template
        )
        frame += 1
    return np.asarray(values, np.complex128)


def _ci16(values: np.ndarray) -> np.ndarray:
    scale = 12_000
    clipped = np.clip(values.real * scale, -32_768, 32_767).astype("<i2")
    imag = np.clip(values.imag * scale, -32_768, 32_767).astype("<i2")
    return np.stack((clipped, imag), axis=-1)


def _refined(
    identity: str,
    sample: int,
    cfo_hz: float,
    *,
    receiver_id: int = 0,
    margin: float = 0.8,
) -> RefinedCandidate:
    return RefinedCandidate(
        identity,
        receiver_id,
        sample,
        37,
        sample + 37,
        cfo_hz,
        cfo_hz,
        0.9,
        0.1,
        margin,
    )


def test_raw_validation_and_waterfall_surface_partial_and_corrupt_geometry() -> None:
    tone = np.exp(2j * np.pi * 125_000 * np.arange(12_000) / RATE)
    values = _ci16(tone)[:, None, :]
    complete = _reader(values)
    waterfall = bounded_waterfall(
        complete,
        WaterfallConfig(
            fft_samples=256,
            frequency_bins=32,
            maximum_time_bins=8,
            block_samples=700,
        ),
    )

    assert waterfall.coverage.observed_fraction == 1.0
    assert waterfall.coverage.transformed_samples <= len(values)
    assert len(waterfall.tiles) == 8
    assert all(len(tile.receiver_power_dbfs[0]) == 32 for tile in waterfall.tiles)
    assert complete.maximum_yielded_samples <= 700
    assert waterfall.maximum_working_set_bytes < 2_000_000

    partial = _SegmentedReader(
        ((0, values[:4000]), (5000, values[5000:9000])),
        sample_count=12_000,
    )
    validation = validate_raw_iq(partial, block_samples=512)
    partial_tiles = bounded_waterfall(
        partial,
        WaterfallConfig(
            fft_samples=256,
            frequency_bins=16,
            maximum_time_bins=4,
            block_samples=512,
        ),
    )
    assert validation.reason == "partial coverage"
    assert validation.missing_samples == 4000
    assert validation.gap_count == 2
    assert partial_tiles.coverage.gap_count == 2

    corrupt = _SegmentedReader(
        ((100, values[:1000]), (0, values[1000:2000])),
        sample_count=2000,
    )
    corrupt_result = validate_raw_iq(corrupt, block_samples=512)
    assert corrupt_result.status is NumericalStatus.INSUFFICIENT
    assert corrupt_result.reason.startswith("corrupt IQ stream:")

    incomplete_survey = sparse_whole_dwell_survey(
        _SegmentedReader(
            ((0, values[:7000]), (8000, values[8000:14_000])),
            sample_count=14_000,
        ),
        {0: ReceiverFrequencyCalibration("rx0", 0.0, "0" * 64)},
        SparseSurveyConfig(maximum_windows=1, maximum_buffered_samples=14_000),
        edge=StarlinkEdge.LOWER,
    )
    assert incomplete_survey.status is NumericalStatus.INSUFFICIENT
    assert incomplete_survey.coverage.incomplete_window_count == 1


def test_sparse_survey_is_whole_dwell_bounded_and_retains_candidate_basins() -> None:
    windows = tuple(
        _pilot_window(epoch=37, absolute_cfo_hz=cfo, seed=index)
        for index, cfo in enumerate((161_170.0, 201_170.0, 241_170.0), start=1)
    )
    values = np.concatenate(tuple(_ci16(window) for window in windows))[:, None, :]
    reader = _reader(values)
    config = SparseSurveyConfig(
        maximum_windows=3,
        probe_samples=14_000,
        maximum_buffered_samples=42_000,
        block_samples=997,
    )
    survey = sparse_whole_dwell_survey(
        reader,
        {0: ReceiverFrequencyCalibration("rx0", 1_170.0, "1" * 64)},
        config,
        edge=StarlinkEdge.LOWER,
    )

    assert survey.status is NumericalStatus.COMPLETE
    assert survey.coverage.complete_window_count == 3
    assert survey.coverage.scheduled_window_count == 3
    assert survey.coverage.time_sample_fraction == 1.0
    assert survey.maximum_working_set_bytes <= 42_000 * 4 + 24
    assert len(survey.candidates) == 24
    for index, expected in enumerate((161_170.0, 201_170.0, 241_170.0)):
        candidates = [item for item in survey.candidates if item.window_index == index]
        assert min(abs(item.absolute_cfo_hz - expected) for item in candidates) < 35


def test_candidate_cloud_preserves_nonfirst_basin_that_forms_continuous_track() -> None:
    observations = []
    for window in range(3):
        # One attractive alias is present only in the first window.
        if window == 0:
            observations.append(
                SurveyCandidate(
                    window,
                    window * 1_000_000,
                    0,
                    "2" * 64,
                    0,
                    window * 1_000_000 + 811,
                    -160_000.0,
                    -160_000.0,
                    0.99,
                    0.95,
                    0.1,
                    0.85,
                    4,
                )
            )
        observations.append(
            SurveyCandidate(
                window,
                window * 1_000_000,
                0,
                "2" * 64,
                1,
                window * 1_000_000 + 127,
                200_000.0 + window * 20_000,
                200_000.0 + window * 20_000,
                0.8,
                0.9,
                0.1,
                0.8,
                4,
            )
        )
    survey = SparseSurveyResult(
        NumericalStatus.COMPLETE,
        "test",
        "sha256:" + "3" * 64,
        SparseSurveyCoverage(3_000_000, 3, 3, 0, 3, 42_000, 0.014, -400_000, 400_000),
        tuple(observations),
        ScientificConfidence.CANDIDATE,
        1,
        "candidate only",
    )
    cloud = build_candidate_cloud(survey, CandidateCloudConfig(maximum_candidates=8))
    tracks = track_candidate_activity(
        cloud,
        ActivityTrackingConfig(maximum_cfo_step_hz=25_000, minimum_observations=3),
    )

    assert len(cloud.candidates) == 4
    assert len(tracks.tracks) == 1
    assert tracks.tracks[0].window_indexes == (0, 1, 2)
    assert tracks.orphan_candidate_count == 1


def test_dense_refinement_doppler_locked_integration_and_tle_contract() -> None:
    calibration = ReceiverFrequencyCalibration("rx0", 1_170.0, "4" * 64)
    starts = (0, RATE, 2 * RATE)
    absolute_cfos = (201_170.0, 202_170.0, 203_170.0)
    windows = tuple(
        DenseRefinementWindow(
            f"candidate-{index}",
            0,
            start,
            _pilot_window(epoch=37, absolute_cfo_hz=cfo, seed=20 + index),
            calibration,
            cfo - calibration.center_hz,
        )
        for index, (start, cfo) in enumerate(zip(starts, absolute_cfos, strict=True))
    )
    refined = dense_refine_candidates(
        windows,
        RATE,
        DenseRefinementConfig(conditioned_cfo_step_hz=10.0),
        edge=StarlinkEdge.LOWER,
    )
    doppler = fit_doppler(refined.refined, RATE, DopplerFitConfig())

    assert refined.status is NumericalStatus.COMPLETE
    assert len(refined.refined) == 3
    assert doppler.motion_class is MotionClass.DYNAMIC
    assert doppler.slope_hz_s == pytest.approx(1000.0, abs=20.0)
    assert doppler.residual_rms_hz is not None and doppler.residual_rms_hz < 20

    length = 512
    rng = np.random.default_rng(9)
    base = rng.normal(size=length) + 1j * rng.normal(size=length)
    frames = []
    for index, start in enumerate(starts):
        time_s = (start + np.arange(length)) / RATE
        delta = time_s - float(doppler.reference_time_s)
        cycles = (
            float(doppler.frequency_at_reference_hz) * delta
            + 0.5 * float(doppler.slope_hz_s) * delta**2
        )
        frames.append(
            LockedFrame(
                f"frame-{index}",
                start,
                base * np.exp(2j * np.pi * cycles + 1j * index * 0.7),
            )
        )
    locked = dedoppler_locked_integration(
        tuple(frames), RATE, doppler, LockedIntegrationConfig(maximum_frames=3)
    )
    assert locked.status is NumericalStatus.COMPLETE
    assert locked.coherent_gain_db == pytest.approx(10 * math.log10(3), abs=0.05)
    assert locked.maximum_working_set_bytes <= 4 * 3 * length * 16

    unavailable = associate_tle_candidate(
        doppler,
        None,
        maximum_frequency_residual_hz=500,
        maximum_slope_residual_hz_s=50,
    )
    associated = associate_tle_candidate(
        doppler,
        (TlePrediction("STARLINK-TEST", "2026-08-19T00:00:00Z", 202_170, 1000),),
        maximum_frequency_residual_hz=500,
        maximum_slope_residual_hz_s=50,
    )
    assert unavailable.status is TleAssociationStatus.UNAVAILABLE
    assert associated.status is TleAssociationStatus.CANDIDATE
    assert associated.candidate_only is True


def test_controls_keep_uncalibrated_positive_candidate_only_and_reject_stationary() -> None:
    calibration = ReceiverFrequencyCalibration("rx0", 0.0, "5" * 64)
    starts = (0, RATE, 2 * RATE)
    windows = tuple(
        DenseRefinementWindow(
            f"control-{index}",
            0,
            start,
            _pilot_window(epoch=37, absolute_cfo_hz=200_000 + index * 1000, seed=30 + index),
            calibration,
            200_000 + index * 1000,
        )
        for index, start in enumerate(starts)
    )
    refined = dense_refine_candidates(
        windows, RATE, DenseRefinementConfig(), edge=StarlinkEdge.LOWER
    )
    qam = qam_handoff(windows, refined, RATE, edge=StarlinkEdge.LOWER)
    dynamic = fit_doppler(refined.refined, RATE, DopplerFitConfig())
    controls = evaluate_candidate_controls(
        windows,
        refined,
        qam,
        dynamic,
        RATE,
        ControlConfig(),
        edge=StarlinkEdge.LOWER,
    )

    assert controls.status is NumericalStatus.COMPLETE
    assert controls.confidence is ScientificConfidence.CANDIDATE
    assert controls.specificity_claimed is False
    assert all(item.passed_research_gate for item in controls.evidence)

    stationary_candidates = tuple(
        _refined(f"stationary-{index}", start, 200_000.0) for index, start in enumerate(starts)
    )
    stationary = fit_doppler(stationary_candidates, RATE, DopplerFitConfig())
    rejected = evaluate_candidate_controls(
        windows,
        refined,
        qam,
        stationary,
        RATE,
        ControlConfig(),
        edge=StarlinkEdge.LOWER,
    )
    assert stationary.motion_class is MotionClass.STATIONARY_CONFOUNDER
    assert rejected.status is NumericalStatus.NO_RESULT
    assert rejected.confidence is ScientificConfidence.REJECTED
    assert all("Doppler track is not dynamic" in item.reasons for item in rejected.evidence)


def test_null_and_missing_dense_windows_are_explicitly_insufficient_or_no_result() -> None:
    calibration = ReceiverFrequencyCalibration("rx0", 0.0, "6" * 64)
    null_window = DenseRefinementWindow(
        "null",
        0,
        0,
        np.zeros(14_000, dtype=np.complex64),
        calibration,
        0.0,
    )
    null_refined = dense_refine_candidates(
        (null_window,), RATE, DenseRefinementConfig(), edge=StarlinkEdge.LOWER
    )
    missing = dense_refine_candidates((), RATE, DenseRefinementConfig(), edge=StarlinkEdge.LOWER)

    assert null_refined.status is NumericalStatus.NO_RESULT
    assert missing.status is NumericalStatus.INSUFFICIENT


def test_scientific_summary_has_bounded_overlays_and_complete_config_lineage() -> None:
    values = _ci16(np.ones(2048, dtype=np.complex128))[:, None, :]
    waterfall = bounded_waterfall(
        _reader(values),
        WaterfallConfig(
            fft_samples=256,
            frequency_bins=8,
            maximum_time_bins=4,
            block_samples=512,
        ),
    )
    observation = SurveyCandidate(
        0,
        0,
        0,
        "a" * 64,
        0,
        37,
        200_000.0,
        200_000.0,
        0.9,
        0.9,
        0.1,
        0.8,
        4,
    )
    cloud = CandidateCloudResult(
        NumericalStatus.COMPLETE,
        "sha256:" + "b" * 64,
        (CloudCandidate("candidate", "sha256:" + "c" * 64, observation),),
        0,
        0,
        ScientificConfidence.CANDIDATE,
    )
    tracks = ActivityTrackingResult(
        NumericalStatus.COMPLETE,
        "sha256:" + "d" * 64,
        (CandidateTrack("track", 0, ("candidate",), (0,), (37,), (200_000.0,), 0, True),),
        0,
        ScientificConfidence.CANDIDATE,
    )
    doppler = fit_doppler(
        (
            _refined("d0", 0, 200_000),
            _refined("d1", RATE, 201_000),
            _refined("d2", 2 * RATE, 202_000),
        ),
        RATE,
        DopplerFitConfig(),
    )
    qam = QamHandoffResult(NumericalStatus.INSUFFICIENT, (), None, True, "not run")
    controls = ControlResult(
        NumericalStatus.COMPLETE,
        "sha256:" + "e" * 64,
        (),
        ScientificConfidence.CANDIDATE,
        False,
        False,
        "candidate only",
    )
    tle = TleAssociationResult(
        TleAssociationStatus.UNAVAILABLE,
        None,
        None,
        None,
        None,
        True,
        "not supplied",
    )

    summary = build_scientific_summary(
        sample_rate_hz=RATE,
        waterfall=waterfall,
        cloud=cloud,
        tracks=tracks,
        doppler=doppler,
        qam=qam,
        controls=controls,
        tle=tle,
    )

    assert summary.candidate_count == 1
    assert summary.track_count == 1
    assert len(summary.candidate_overlay) == 1
    assert len(summary.track_overlays) == 1
    assert len(summary.lineage_config_digests) == 5
    assert summary.confidence is ScientificConfidence.CANDIDATE


def test_retro_short_slice_exercises_waterfall_and_sparse_survey_without_full_dwell_claim() -> None:
    root = Path("/srv/bulk/leo/test-corpus/retro-positive-68p7")
    fixture = json.loads((root / "fixture-manifest.json").read_bytes())
    metadata = fixture["metadata"]
    expected = metadata["candidate_expectation"]
    raw = np.memmap(
        root / "recording.ci16",
        dtype="<i2",
        mode="r",
        shape=(metadata["selection"]["sample_count"], 2, 2),
    )
    reader = _reader(np.asarray(raw))
    tiles = bounded_waterfall(
        reader,
        WaterfallConfig(
            fft_samples=256,
            frequency_bins=32,
            maximum_time_bins=8,
            block_samples=4096,
        ),
    )
    survey = sparse_whole_dwell_survey(
        reader,
        {
            0: ReceiverFrequencyCalibration("retro-rx0", 0.0, "7" * 64),
            1: ReceiverFrequencyCalibration("retro-rx1", 0.0, "8" * 64),
        },
        SparseSurveyConfig(
            probe_samples=25_000,
            maximum_windows=1,
            maximum_buffered_samples=25_000,
            block_samples=4096,
        ),
        edge=StarlinkEdge.LOWER,
    )

    assert tiles.coverage.observed_fraction == 1.0
    assert survey.status is NumericalStatus.COMPLETE
    for receiver, expected_cfo in enumerate(expected["receiver_cfo_hz"]):
        receiver_candidates = [item for item in survey.candidates if item.receiver_id == receiver]
        assert min(abs(item.absolute_cfo_hz - expected_cfo) for item in receiver_candidates) < 35
