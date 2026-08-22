"""Trajectory-conditioned accounting for multi-component pilot replay.

Replay deliberately evaluates every accepted trajectory independently.  A
global rank-zero pilot winner is therefore not a valid baseline for every
trajectory when several CFO components occupy the same probe.  This module
associates one retained acquisition basin with each replayed trajectory before
computing before/after statistics; unmatched trajectories remain explicit
rather than being compared with an unrelated signal.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from leo.analysis.starlink.pilot_methods import (
    PilotMethod,
    PilotMethodScore,
    PilotProbeDetection,
)
from leo.analysis.starlink.trajectories import PolynomialTrajectory


@dataclass(frozen=True, slots=True)
class TrajectoryConditionedBaseline:
    """One acquisition basin geometrically associated with a trajectory."""

    candidate_rank: int
    association_error_hz: float
    trajectory_tracking_cfo_hz: float
    scores: tuple[PilotMethodScore, ...]


@dataclass(frozen=True, slots=True)
class TrajectoryConditionedEvaluation:
    """One replay row with its trajectory-specific and global baselines."""

    trajectory_id: str
    sample_start: int
    time_s: float
    detector_method: PilotMethod
    corrected_margin: float
    global_baseline_margin: float | None
    baseline_candidate_rank: int | None
    baseline_association_error_hz: float | None
    baseline_tracking_cfo_hz: float | None
    baseline_margin: float | None


@dataclass(frozen=True, slots=True)
class ReplayTransitionCounts:
    positive_to_positive: int = 0
    positive_to_negative: int = 0
    negative_to_positive: int = 0
    negative_to_negative: int = 0

    @property
    def baseline_positive(self) -> int:
        return self.positive_to_positive + self.positive_to_negative

    @property
    def corrected_positive(self) -> int:
        return self.positive_to_positive + self.negative_to_positive


@dataclass(frozen=True, slots=True)
class TrajectoryReplaySummary:
    trajectory_id: str
    evaluation_count: int
    associated_count: int
    unassociated_count: int
    unassociated_corrected_positive_count: int
    transitions: ReplayTransitionCounts


@dataclass(frozen=True, slots=True)
class TrajectoryConditionedReplayAccounting:
    """Trajectory-level and unique-probe views of one detector method."""

    association_gate_hz: float
    positive_margin: float
    evaluations: tuple[TrajectoryConditionedEvaluation, ...]
    trajectory_summaries: tuple[TrajectoryReplaySummary, ...]
    associated_transitions: ReplayTransitionCounts
    unique_probe_transitions: ReplayTransitionCounts


def _score(
    scores: tuple[PilotMethodScore, ...], method: PilotMethod
) -> PilotMethodScore | None:
    return next((score for score in scores if score.method is method), None)


def _candidate_inventory(
    detection: PilotProbeDetection,
) -> tuple[tuple[int, tuple[PilotMethodScore, ...]], ...]:
    if detection.candidates:
        return tuple((candidate.rank, candidate.scores) for candidate in detection.candidates)
    return ((0, detection.scores),) if detection.scores else ()


def associate_trajectory_baseline(
    detection: PilotProbeDetection,
    trajectory: PolynomialTrajectory,
    *,
    frequency_offset_hz: float,
    association_gate_hz: float,
) -> TrajectoryConditionedBaseline | None:
    """Return the nearest same-method basin only when it matches the trajectory."""

    if not math.isfinite(frequency_offset_hz):
        raise ValueError("trajectory baseline frequency offset must be finite")
    if not math.isfinite(association_gate_hz) or association_gate_hz <= 0.0:
        raise ValueError("trajectory baseline association gate must be finite and positive")
    predicted_hz = float(trajectory.frequency_hz(detection.time_s)) + frequency_offset_hz
    choices: list[
        tuple[float, int, PilotMethodScore, tuple[PilotMethodScore, ...]]
    ] = []
    for rank, scores in _candidate_inventory(detection):
        trajectory_score = _score(scores, trajectory.method)
        if trajectory_score is None:
            continue
        error_hz = abs(trajectory_score.tracking_cfo_hz - predicted_hz)
        choices.append((error_hz, rank, trajectory_score, scores))
    if not choices:
        return None
    error_hz, rank, trajectory_score, scores = min(
        choices,
        key=lambda item: (item[0], item[1]),
    )
    if error_hz > association_gate_hz:
        return None
    return TrajectoryConditionedBaseline(
        candidate_rank=rank,
        association_error_hz=error_hz,
        trajectory_tracking_cfo_hz=trajectory_score.tracking_cfo_hz,
        scores=scores,
    )


def _number(row: Mapping[str, Any], key: str) -> float:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"trajectory replay {key} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"trajectory replay {key} must be finite")
    return result


def _integer(row: Mapping[str, Any], key: str) -> int:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"trajectory replay {key} must be a nonnegative integer")
    return value


def trajectory_conditioned_evaluations(
    detections: tuple[PilotProbeDetection, ...],
    representatives: tuple[tuple[str, PolynomialTrajectory], ...],
    replay: tuple[Mapping[str, Any], ...],
    *,
    frequency_offsets_hz: Mapping[str, float],
    association_gate_hz: float,
) -> tuple[TrajectoryConditionedEvaluation, ...]:
    """Bind each replay result to the same physical baseline component, if present."""

    by_sample = {item.sample_start: item for item in detections}
    if len(by_sample) != len(detections):
        raise ValueError("trajectory accounting detections must have unique sample starts")
    by_trajectory = {trajectory.trajectory_id: trajectory for _, trajectory in representatives}
    if len(by_trajectory) != len(representatives):
        raise ValueError("trajectory accounting representatives must be unique")
    if set(frequency_offsets_hz) != set(by_trajectory):
        raise ValueError("trajectory accounting offsets must exactly cover representatives")

    result: list[TrajectoryConditionedEvaluation] = []
    identities: set[tuple[str, int, PilotMethod]] = set()
    for row in replay:
        trajectory_id = row.get("trajectory_id")
        if not isinstance(trajectory_id, str) or trajectory_id not in by_trajectory:
            raise ValueError("trajectory replay row names an unknown trajectory")
        sample_start = _integer(row, "sample_start")
        detection = by_sample.get(sample_start)
        if detection is None:
            raise ValueError("trajectory replay row lies outside the detection inventory")
        method_value = row.get("detector_method")
        try:
            method = PilotMethod(method_value)
        except (TypeError, ValueError) as error:
            raise ValueError("trajectory replay detector method is invalid") from error
        identity = (trajectory_id, sample_start, method)
        if identity in identities:
            raise ValueError("trajectory replay rows must be unique")
        identities.add(identity)

        trajectory = by_trajectory[trajectory_id]
        match = associate_trajectory_baseline(
            detection,
            trajectory,
            frequency_offset_hz=frequency_offsets_hz[trajectory_id],
            association_gate_hz=association_gate_hz,
        )
        baseline_score = None if match is None else _score(match.scores, method)
        global_score = _score(detection.scores, method)
        result.append(
            TrajectoryConditionedEvaluation(
                trajectory_id=trajectory_id,
                sample_start=sample_start,
                time_s=_number(row, "time_s"),
                detector_method=method,
                corrected_margin=_number(row, "corrected_margin"),
                global_baseline_margin=None if global_score is None else global_score.margin,
                baseline_candidate_rank=None if match is None else match.candidate_rank,
                baseline_association_error_hz=(
                    None if match is None else match.association_error_hz
                ),
                baseline_tracking_cfo_hz=(
                    None if match is None else match.trajectory_tracking_cfo_hz
                ),
                baseline_margin=None if baseline_score is None else baseline_score.margin,
            )
        )
    return tuple(
        sorted(
            result,
            key=lambda item: (
                item.trajectory_id,
                item.sample_start,
                item.detector_method.value,
            ),
        )
    )


def _transitions(
    pairs: list[tuple[bool, bool]],
) -> ReplayTransitionCounts:
    counts: dict[tuple[bool, bool], int] = defaultdict(int)
    for pair in pairs:
        counts[pair] += 1
    return ReplayTransitionCounts(
        positive_to_positive=counts[(True, True)],
        positive_to_negative=counts[(True, False)],
        negative_to_positive=counts[(False, True)],
        negative_to_negative=counts[(False, False)],
    )


def summarize_trajectory_conditioned_replay(
    evaluations: tuple[TrajectoryConditionedEvaluation, ...],
    *,
    detector_method: PilotMethod = PilotMethod.GLRT64,
    association_gate_hz: float,
    positive_margin: float = 0.05,
) -> TrajectoryConditionedReplayAccounting:
    """Summarize matched trajectory evaluations and best-of-trajectory probe results."""

    if not math.isfinite(positive_margin):
        raise ValueError("trajectory accounting positive margin must be finite")
    if not math.isfinite(association_gate_hz) or association_gate_hz <= 0.0:
        raise ValueError("trajectory accounting association gate must be finite and positive")
    selected = tuple(item for item in evaluations if item.detector_method is detector_method)
    by_trajectory: dict[str, list[TrajectoryConditionedEvaluation]] = defaultdict(list)
    by_sample: dict[int, list[TrajectoryConditionedEvaluation]] = defaultdict(list)
    associated_pairs: list[tuple[bool, bool]] = []
    for item in selected:
        by_trajectory[item.trajectory_id].append(item)
        by_sample[item.sample_start].append(item)
        if item.baseline_margin is not None:
            associated_pairs.append(
                (
                    item.baseline_margin >= positive_margin,
                    item.corrected_margin >= positive_margin,
                )
            )

    trajectory_summaries = []
    for trajectory_id, values in sorted(by_trajectory.items()):
        matched = [item for item in values if item.baseline_margin is not None]
        pairs = [
            (
                item.baseline_margin >= positive_margin,
                item.corrected_margin >= positive_margin,
            )
            for item in matched
            if item.baseline_margin is not None
        ]
        unmatched = [item for item in values if item.baseline_margin is None]
        trajectory_summaries.append(
            TrajectoryReplaySummary(
                trajectory_id=trajectory_id,
                evaluation_count=len(values),
                associated_count=len(matched),
                unassociated_count=len(unmatched),
                unassociated_corrected_positive_count=sum(
                    item.corrected_margin >= positive_margin for item in unmatched
                ),
                transitions=_transitions(pairs),
            )
        )

    unique_pairs = []
    for values in by_sample.values():
        global_margins = [
            item.global_baseline_margin
            for item in values
            if item.global_baseline_margin is not None
        ]
        if not global_margins:
            continue
        unique_pairs.append(
            (
                max(global_margins) >= positive_margin,
                max(item.corrected_margin for item in values) >= positive_margin,
            )
        )
    return TrajectoryConditionedReplayAccounting(
        association_gate_hz=association_gate_hz,
        positive_margin=positive_margin,
        evaluations=selected,
        trajectory_summaries=tuple(trajectory_summaries),
        associated_transitions=_transitions(associated_pairs),
        unique_probe_transitions=_transitions(unique_pairs),
    )
