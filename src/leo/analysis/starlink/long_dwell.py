"""Bounded whole-dwell survey, candidate lineage, and locked handoff primitives."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import cast

import numpy as np

from leo.analysis._streaming import IqStreamError, validated_blocks
from leo.analysis.qam import (
    CombinedPilotQamResult,
    PilotQamResult,
    analyze_pilot_qam,
    combine_receiver_qam,
)
from leo.analysis.starlink.acquisition import (
    NumericalStatus,
    ReceiverFrequencyCalibration,
    SymbolwiseAcquisitionConfig,
    acquire_symbolwise,
)
from leo.contracts.digests import canonical_digest
from leo.pipeline import IqReader


class ScientificConfidence(StrEnum):
    """Evidence strength, deliberately unrelated to compute tier."""

    UNASSESSED = "unassessed"
    CANDIDATE = "candidate"
    QUALIFIED = "qualified"
    REJECTED = "rejected"
    INSUFFICIENT = "insufficient"


@dataclass(frozen=True, slots=True)
class RawValidationResult:
    status: NumericalStatus
    expected_samples: int
    observed_samples: int
    missing_samples: int
    gap_count: int
    coverage_fraction: float
    maximum_block_samples: int
    reason: str


def validate_raw_iq(reader: IqReader, *, block_samples: int) -> RawValidationResult:
    """Validate declared stream geometry without retaining the dwell."""

    observed = 0
    gaps = 0
    cursor = 0
    maximum = 0
    try:
        for block in validated_blocks(reader, block_samples=block_samples):
            start = block.metadata.session_sample_start
            if start > cursor:
                gaps += 1
            observed += block.metadata.sample_count
            maximum = max(maximum, block.metadata.sample_count)
            cursor = start + block.metadata.sample_count
    except (IqStreamError, ValueError) as exc:
        return RawValidationResult(
            NumericalStatus.INSUFFICIENT,
            reader.sample_count,
            observed,
            max(0, reader.sample_count - observed),
            gaps,
            observed / reader.sample_count if reader.sample_count else 0.0,
            maximum,
            f"corrupt IQ stream: {exc}",
        )
    if cursor < reader.sample_count:
        gaps += 1
    missing = reader.sample_count - observed
    if observed == 0:
        status = NumericalStatus.INSUFFICIENT
        reason = "no IQ samples were available"
    else:
        status = NumericalStatus.COMPLETE
        reason = "complete coverage" if not missing and not gaps else "partial coverage"
    return RawValidationResult(
        status,
        reader.sample_count,
        observed,
        missing,
        gaps,
        observed / reader.sample_count if reader.sample_count else 0.0,
        maximum,
        reason,
    )


@dataclass(frozen=True, slots=True)
class SparseSurveyConfig:
    probe_samples: int = 14_000
    maximum_windows: int = 24
    block_samples: int = 262_144
    maximum_buffered_samples: int = 500_000
    residual_cfo_min_hz: float = -400_000.0
    residual_cfo_max_hz: float = 400_000.0
    coarse_cfo_step_hz: float = 80_000.0
    retained_candidates_per_search: int = 8

    def __post_init__(self) -> None:
        integer_values = (
            self.probe_samples,
            self.maximum_windows,
            self.block_samples,
            self.maximum_buffered_samples,
            self.retained_candidates_per_search,
        )
        if any(isinstance(value, bool) or value <= 0 for value in integer_values):
            raise ValueError("survey integer budgets must be positive")
        if self.probe_samples * self.maximum_windows > self.maximum_buffered_samples:
            raise ValueError("survey window budget exceeds maximum_buffered_samples")
        if self.residual_cfo_min_hz >= self.residual_cfo_max_hz:
            raise ValueError("survey CFO range must be non-empty")
        if self.coarse_cfo_step_hz <= 0 or not math.isfinite(self.coarse_cfo_step_hz):
            raise ValueError("survey CFO step must be finite and positive")

    @property
    def digest(self) -> str:
        return canonical_digest(asdict(self))


@dataclass(frozen=True, slots=True)
class SurveyCandidate:
    window_index: int
    window_sample_start: int
    receiver_id: int
    receiver_calibration_sha256: str
    rank_within_search: int
    absolute_epoch_sample: int
    residual_cfo_hz: float
    absolute_cfo_hz: float
    acquire_score: float
    verify_score: float
    control_score: float
    verify_minus_control_margin: float
    frame_support: int


@dataclass(frozen=True, slots=True)
class SparseSurveyCoverage:
    declared_dwell_samples: int
    scheduled_window_count: int
    complete_window_count: int
    incomplete_window_count: int
    searched_receiver_window_count: int
    searched_sample_count: int
    time_sample_fraction: float
    residual_cfo_min_hz: float
    residual_cfo_max_hz: float


@dataclass(frozen=True, slots=True)
class SparseSurveyResult:
    status: NumericalStatus
    algorithm_version: str
    config_digest: str
    coverage: SparseSurveyCoverage
    candidates: tuple[SurveyCandidate, ...]
    confidence: ScientificConfidence
    maximum_working_set_bytes: int
    reason: str


def sparse_whole_dwell_survey(
    reader: IqReader,
    calibrations: dict[int, ReceiverFrequencyCalibration],
    config: SparseSurveyConfig,
) -> SparseSurveyResult:
    """Sample evenly across the whole dwell and preserve every retained basin."""

    if set(calibrations) != set(reader.receiver_ids):
        raise ValueError("every receiver requires exactly one immutable calibration")
    starts = _even_window_starts(reader.sample_count, config.probe_samples, config.maximum_windows)
    receiver_count = len(reader.receiver_ids)
    buffers = [np.zeros((config.probe_samples, receiver_count, 2), dtype="<i2") for _ in starts]
    observed = np.zeros(len(starts), dtype=np.int64)
    try:
        for block in validated_blocks(reader, block_samples=config.block_samples):
            block_start = block.metadata.session_sample_start
            block_stop = block_start + block.metadata.sample_count
            for index, window_start in enumerate(starts):
                window_stop = window_start + config.probe_samples
                overlap_start = max(block_start, window_start)
                overlap_stop = min(block_stop, window_stop)
                if overlap_start >= overlap_stop:
                    continue
                source_start = overlap_start - block_start
                source_stop = overlap_stop - block_start
                target_start = overlap_start - window_start
                target_stop = overlap_stop - window_start
                buffers[index][target_start:target_stop] = block.samples[source_start:source_stop]
                observed[index] += overlap_stop - overlap_start
    except (IqStreamError, ValueError) as exc:
        return _empty_survey(reader, config, starts, f"corrupt IQ stream: {exc}")

    candidates: list[SurveyCandidate] = []
    complete_windows = 0
    searched_receiver_windows = 0
    acquisition_config = SymbolwiseAcquisitionConfig(
        residual_cfo_min_hz=config.residual_cfo_min_hz,
        residual_cfo_max_hz=config.residual_cfo_max_hz,
        coarse_cfo_step_hz=config.coarse_cfo_step_hz,
        retained_candidate_count=config.retained_candidates_per_search,
        maximum_probe_samples=config.probe_samples,
    )
    for window_index, (window_start, buffer) in enumerate(zip(starts, buffers, strict=True)):
        if observed[window_index] != config.probe_samples:
            continue
        complete_windows += 1
        for receiver_index, receiver_id in enumerate(reader.receiver_ids):
            searched_receiver_windows += 1
            values = _ci16_complex(buffer[:, receiver_index])
            acquired = acquire_symbolwise(
                values,
                reader.sample_rate_hz,
                calibrations[receiver_id],
                config=acquisition_config,
            )
            for item in acquired.candidates:
                candidates.append(
                    SurveyCandidate(
                        window_index,
                        window_start,
                        receiver_id,
                        calibrations[receiver_id].calibration_sha256,
                        item.rank,
                        window_start + item.refined_epoch_sample,
                        item.residual_cfo_hz,
                        item.absolute_cfo_hz,
                        item.acquire_score,
                        item.verify_score,
                        item.conditioned_control_score,
                        item.verify_minus_control_margin,
                        item.frame_support,
                    )
                )
    coverage = SparseSurveyCoverage(
        reader.sample_count,
        len(starts),
        complete_windows,
        len(starts) - complete_windows,
        searched_receiver_windows,
        complete_windows * config.probe_samples,
        (
            min(1.0, complete_windows * config.probe_samples / reader.sample_count)
            if reader.sample_count
            else 0.0
        ),
        config.residual_cfo_min_hz,
        config.residual_cfo_max_hz,
    )
    if complete_windows == 0:
        status = NumericalStatus.INSUFFICIENT
        confidence = ScientificConfidence.INSUFFICIENT
        reason = "no complete sparse survey window"
    elif not candidates:
        status = NumericalStatus.NO_RESULT
        confidence = ScientificConfidence.UNASSESSED
        reason = "bounded sparse survey produced no acquisition basin"
    else:
        status = NumericalStatus.COMPLETE
        confidence = ScientificConfidence.CANDIDATE
        reason = "candidate cloud only; detection thresholds are not calibrated"
    buffered_bytes = sum(buffer.nbytes for buffer in buffers) + observed.nbytes
    return SparseSurveyResult(
        status,
        "sparse-whole-dwell-survey-v1",
        config.digest,
        coverage,
        tuple(candidates),
        confidence,
        buffered_bytes,
        reason,
    )


@dataclass(frozen=True, slots=True)
class CandidateCloudConfig:
    maximum_candidates: int = 64
    minimum_margin: float = 0.0
    epoch_basin_separation_samples: int = 20
    cfo_basin_separation_hz: float = 20_000.0

    def __post_init__(self) -> None:
        if self.maximum_candidates <= 0 or self.epoch_basin_separation_samples <= 0:
            raise ValueError("candidate cloud count and epoch separation must be positive")
        if (
            not math.isfinite(self.minimum_margin)
            or not math.isfinite(self.cfo_basin_separation_hz)
            or self.cfo_basin_separation_hz <= 0
        ):
            raise ValueError("candidate cloud margins and CFO separation must be finite")

    @property
    def digest(self) -> str:
        return canonical_digest(asdict(self))


@dataclass(frozen=True, slots=True)
class CloudCandidate:
    candidate_id: str
    parent_survey_config_digest: str
    observation: SurveyCandidate


@dataclass(frozen=True, slots=True)
class CandidateCloudResult:
    status: NumericalStatus
    config_digest: str
    candidates: tuple[CloudCandidate, ...]
    rejected_below_margin: int
    truncated_candidate_count: int
    confidence: ScientificConfidence


def build_candidate_cloud(
    survey: SparseSurveyResult, config: CandidateCloudConfig
) -> CandidateCloudResult:
    """Build a deterministic, explicitly truncated multi-basin cloud."""

    eligible = [
        item
        for item in survey.candidates
        if item.verify_minus_control_margin >= config.minimum_margin
    ]
    rejected = len(survey.candidates) - len(eligible)
    eligible.sort(
        key=lambda item: (
            item.verify_minus_control_margin,
            item.verify_score,
            item.acquire_score,
            -item.window_index,
            -item.receiver_id,
            -item.rank_within_search,
        ),
        reverse=True,
    )
    retained: list[SurveyCandidate] = []
    for item in eligible:
        if any(
            other.window_index == item.window_index
            and other.receiver_id == item.receiver_id
            and abs(other.absolute_epoch_sample - item.absolute_epoch_sample)
            < config.epoch_basin_separation_samples
            and abs(other.absolute_cfo_hz - item.absolute_cfo_hz) < config.cfo_basin_separation_hz
            for other in retained
        ):
            continue
        retained.append(item)
        if len(retained) == config.maximum_candidates:
            break
    cloud = tuple(
        CloudCandidate(
            canonical_digest(
                {
                    "survey_config": survey.config_digest,
                    "window": item.window_index,
                    "receiver": item.receiver_id,
                    "epoch": item.absolute_epoch_sample,
                    "residual_cfo_hz": round(item.residual_cfo_hz, 6),
                }
            ),
            survey.config_digest,
            item,
        )
        for item in retained
    )
    if survey.status is NumericalStatus.INSUFFICIENT:
        status = NumericalStatus.INSUFFICIENT
        confidence = ScientificConfidence.INSUFFICIENT
    elif cloud:
        status = NumericalStatus.COMPLETE
        confidence = ScientificConfidence.CANDIDATE
    else:
        status = NumericalStatus.NO_RESULT
        confidence = ScientificConfidence.UNASSESSED
    return CandidateCloudResult(
        status,
        config.digest,
        cloud,
        rejected,
        max(0, len(eligible) - len(cloud)),
        confidence,
    )


@dataclass(frozen=True, slots=True)
class ActivityTrackingConfig:
    maximum_window_gap: int = 2
    maximum_cfo_step_hz: float = 30_000.0
    minimum_observations: int = 2

    @property
    def digest(self) -> str:
        return canonical_digest(asdict(self))


@dataclass(frozen=True, slots=True)
class CandidateTrack:
    track_id: str
    receiver_id: int
    candidate_ids: tuple[str, ...]
    window_indexes: tuple[int, ...]
    sample_positions: tuple[int, ...]
    absolute_cfo_hz: tuple[float, ...]
    maximum_window_gap: int
    continuous: bool


@dataclass(frozen=True, slots=True)
class ActivityTrackingResult:
    status: NumericalStatus
    config_digest: str
    tracks: tuple[CandidateTrack, ...]
    orphan_candidate_count: int
    confidence: ScientificConfidence


def track_candidate_activity(
    cloud: CandidateCloudResult, config: ActivityTrackingConfig
) -> ActivityTrackingResult:
    """Greedily link receiver-local basins while retaining all lineage IDs."""

    if config.maximum_window_gap <= 0 or config.minimum_observations <= 0:
        raise ValueError("tracking window and observation bounds must be positive")
    if config.maximum_cfo_step_hz <= 0:
        raise ValueError("maximum_cfo_step_hz must be positive")
    pending = sorted(
        cloud.candidates,
        key=lambda item: (
            item.observation.window_index,
            item.observation.receiver_id,
            -item.observation.verify_minus_control_margin,
        ),
    )
    tracks: list[list[CloudCandidate]] = []
    for candidate in pending:
        choices = []
        for index, track in enumerate(tracks):
            last = track[-1]
            window_gap = candidate.observation.window_index - last.observation.window_index
            if (
                candidate.observation.receiver_id == last.observation.receiver_id
                and 0 < window_gap <= config.maximum_window_gap
                and abs(candidate.observation.absolute_cfo_hz - last.observation.absolute_cfo_hz)
                <= config.maximum_cfo_step_hz * window_gap
            ):
                choices.append(
                    (
                        abs(
                            candidate.observation.absolute_cfo_hz - last.observation.absolute_cfo_hz
                        ),
                        index,
                    )
                )
        if choices:
            tracks[min(choices)[1]].append(candidate)
        else:
            tracks.append([candidate])
    complete: list[CandidateTrack] = []
    orphans = 0
    for track in tracks:
        if len(track) < config.minimum_observations:
            orphans += len(track)
            continue
        windows = tuple(item.observation.window_index for item in track)
        maximum_gap = max(
            (right - left for left, right in zip(windows, windows[1:], strict=False)),
            default=0,
        )
        identity = canonical_digest({"candidate_ids": [item.candidate_id for item in track]})
        complete.append(
            CandidateTrack(
                identity,
                track[0].observation.receiver_id,
                tuple(item.candidate_id for item in track),
                windows,
                tuple(item.observation.absolute_epoch_sample for item in track),
                tuple(item.observation.absolute_cfo_hz for item in track),
                maximum_gap,
                maximum_gap <= config.maximum_window_gap,
            )
        )
    return ActivityTrackingResult(
        NumericalStatus.COMPLETE if complete else NumericalStatus.NO_RESULT,
        config.digest,
        tuple(complete),
        orphans,
        ScientificConfidence.CANDIDATE if complete else ScientificConfidence.UNASSESSED,
    )


@dataclass(frozen=True, slots=True)
class DenseRefinementConfig:
    residual_cfo_radius_hz: float = 2_000.0
    conditioned_cfo_step_hz: float = 10.0
    maximum_windows: int = 32
    maximum_probe_samples: int = 50_000

    def __post_init__(self) -> None:
        if (
            not math.isfinite(self.residual_cfo_radius_hz)
            or self.residual_cfo_radius_hz <= 0
            or not math.isfinite(self.conditioned_cfo_step_hz)
            or self.conditioned_cfo_step_hz <= 0
        ):
            raise ValueError("dense CFO radius and step must be finite and positive")
        if self.maximum_windows <= 0 or self.maximum_probe_samples <= 0:
            raise ValueError("dense window and probe budgets must be positive")

    @property
    def digest(self) -> str:
        return canonical_digest(asdict(self))


@dataclass(frozen=True, slots=True)
class DenseRefinementWindow:
    candidate_id: str
    receiver_id: int
    sample_start: int
    samples: np.ndarray
    calibration: ReceiverFrequencyCalibration
    initial_residual_cfo_hz: float


@dataclass(frozen=True, slots=True)
class RefinedCandidate:
    candidate_id: str
    receiver_id: int
    sample_start: int
    local_epoch_sample: int
    absolute_epoch_sample: int
    residual_cfo_hz: float
    absolute_cfo_hz: float
    verify_score: float
    control_score: float
    verify_minus_control_margin: float


@dataclass(frozen=True, slots=True)
class DenseRefinementResult:
    status: NumericalStatus
    config_digest: str
    refined: tuple[RefinedCandidate, ...]
    attempted_window_count: int
    confidence: ScientificConfidence


def dense_refine_candidates(
    windows: tuple[DenseRefinementWindow, ...],
    sample_rate_hz: float,
    config: DenseRefinementConfig,
) -> DenseRefinementResult:
    if len(windows) > config.maximum_windows:
        raise ValueError("dense refinement exceeds maximum_windows")
    refined = []
    for window in windows:
        samples = np.asarray(window.samples)
        if samples.ndim != 1 or samples.size > config.maximum_probe_samples:
            raise ValueError("dense refinement window is malformed or over budget")
        radius = config.residual_cfo_radius_hz
        acquired = acquire_symbolwise(
            samples,
            sample_rate_hz,
            window.calibration,
            config=SymbolwiseAcquisitionConfig(
                residual_cfo_min_hz=window.initial_residual_cfo_hz - radius,
                residual_cfo_max_hz=window.initial_residual_cfo_hz + radius,
                coarse_cfo_step_hz=radius,
                fine_cfo_radius_hz=radius,
                fine_cfo_step_hz=max(50.0, config.conditioned_cfo_step_hz * 5),
                conditioned_cfo_radius_hz=min(500.0, radius),
                conditioned_cfo_step_hz=config.conditioned_cfo_step_hz,
                maximum_probe_samples=config.maximum_probe_samples,
            ),
        )
        winner = acquired.winner
        if winner is None:
            continue
        refined.append(
            RefinedCandidate(
                window.candidate_id,
                window.receiver_id,
                window.sample_start,
                winner.refined_epoch_sample,
                window.sample_start + winner.refined_epoch_sample,
                winner.residual_cfo_hz,
                winner.absolute_cfo_hz,
                winner.verify_score,
                winner.conditioned_control_score,
                winner.verify_minus_control_margin,
            )
        )
    if refined:
        status = NumericalStatus.COMPLETE
        confidence = ScientificConfidence.CANDIDATE
    elif windows:
        status = NumericalStatus.NO_RESULT
        confidence = ScientificConfidence.UNASSESSED
    else:
        status = NumericalStatus.INSUFFICIENT
        confidence = ScientificConfidence.INSUFFICIENT
    return DenseRefinementResult(status, config.digest, tuple(refined), len(windows), confidence)


@dataclass(frozen=True, slots=True)
class QamHandoffResult:
    status: NumericalStatus
    receiver_results: tuple[PilotQamResult, ...]
    combined: CombinedPilotQamResult | None
    candidate_only: bool
    reason: str
    receiver_ids: tuple[int, ...] = ()
    receiver_epoch_samples: tuple[int, ...] = ()


def qam_handoff(
    windows: tuple[DenseRefinementWindow, ...],
    refined: DenseRefinementResult,
    sample_rate_hz: float,
) -> QamHandoffResult:
    """Condition QAM only on dense winners; this is not payload decoding."""

    by_id = {window.candidate_id: window for window in windows}
    best_by_receiver: dict[int, RefinedCandidate] = {}
    for item in refined.refined:
        previous = best_by_receiver.get(item.receiver_id)
        if previous is None or (
            item.verify_minus_control_margin,
            item.verify_score,
            -item.absolute_epoch_sample,
        ) > (
            previous.verify_minus_control_margin,
            previous.verify_score,
            -previous.absolute_epoch_sample,
        ):
            best_by_receiver[item.receiver_id] = item
    results = []
    for receiver_id in sorted(best_by_receiver):
        item = best_by_receiver[receiver_id]
        window = by_id.get(item.candidate_id)
        if window is None:
            raise ValueError("refinement lineage has no source window")
        results.append(
            analyze_pilot_qam(
                window.samples,
                sample_rate_hz,
                epoch_sample=item.local_epoch_sample,
                absolute_cfo_hz=item.absolute_cfo_hz,
            )
        )
    complete = tuple(item for item in results if item.status is NumericalStatus.COMPLETE)
    combined = combine_receiver_qam(complete) if len(complete) >= 2 else None
    if not windows:
        status = NumericalStatus.INSUFFICIENT
        reason = "no dense winner was supplied to QAM"
    elif complete:
        status = NumericalStatus.COMPLETE
        reason = "known-pilot QAM evidence; payload was not decoded"
    else:
        status = NumericalStatus.NO_RESULT
        reason = "dense winners had no complete known-pilot frame"
    return QamHandoffResult(
        status,
        cast(tuple[PilotQamResult, ...], tuple(results)),
        combined,
        True,
        reason,
        tuple(sorted(best_by_receiver)),
        tuple(best_by_receiver[item].absolute_epoch_sample for item in sorted(best_by_receiver)),
    )


def _even_window_starts(sample_count: int, window: int, maximum: int) -> tuple[int, ...]:
    if sample_count < window:
        return ()
    possible = sample_count - window
    count = min(maximum, possible // window + 1)
    if count <= 1:
        return (0,)
    return tuple(sorted({round(index * possible / (count - 1)) for index in range(count)}))


def _empty_survey(
    reader: IqReader,
    config: SparseSurveyConfig,
    starts: tuple[int, ...],
    reason: str,
) -> SparseSurveyResult:
    return SparseSurveyResult(
        NumericalStatus.INSUFFICIENT,
        "sparse-whole-dwell-survey-v1",
        config.digest,
        SparseSurveyCoverage(
            reader.sample_count,
            len(starts),
            0,
            len(starts),
            0,
            0,
            0.0,
            config.residual_cfo_min_hz,
            config.residual_cfo_max_hz,
        ),
        (),
        ScientificConfidence.INSUFFICIENT,
        0,
        reason,
    )


def _ci16_complex(values: np.ndarray) -> np.ndarray:
    return np.asarray(
        (values[:, 0].astype(np.float32) + 1j * values[:, 1].astype(np.float32)) / 32_768.0,
        dtype=np.complex128,
    )
