"""Build and render derived trajectory-conditioned replay accounting."""

from __future__ import annotations

import io
import math
from collections import Counter, defaultdict
from collections.abc import Mapping
from threading import RLock
from typing import Any

import matplotlib

matplotlib.use("Agg")
import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from leo.analysis.starlink.pilot_methods import PilotMethod, PilotProbeDetection
from leo.analysis.starlink.trajectories import PolynomialTrajectory
from leo.analysis.starlink.trajectory_accounting import (
    ReplayTransitionCounts,
    summarize_trajectory_conditioned_replay,
    trajectory_conditioned_evaluations,
)
from leo.contracts.digests import Sha256Digest
from leo.contracts.trajectory_accounting import (
    ReplayTransitionCountsV1,
    TrajectoryAccountingConfigV1,
    TrajectoryAccountingConfigV2,
    TrajectoryConditionedEvaluationV1,
    TrajectoryConditionedEvaluationV2,
    TrajectoryConditionedReplayAccountingV1,
    TrajectoryConditionedReplayAccountingV2,
    TrajectoryReplayComparisonSummaryV2,
    TrajectoryReplaySummaryV1,
)

_RENDER_LOCK = RLock()


def _transition_counts(value: ReplayTransitionCounts) -> ReplayTransitionCountsV1:
    return ReplayTransitionCountsV1(
        positive_to_positive=value.positive_to_positive,
        positive_to_negative=value.positive_to_negative,
        negative_to_positive=value.negative_to_positive,
        negative_to_negative=value.negative_to_negative,
    )


def build_trajectory_conditioned_accounting_v1(
    detections: tuple[PilotProbeDetection, ...],
    representatives: tuple[tuple[str, PolynomialTrajectory], ...],
    replay: tuple[Mapping[str, Any], ...],
    *,
    frequency_offsets_hz: Mapping[str, float],
    pilot_scan_digest: Sha256Digest,
    trajectory_bank_digest: Sha256Digest,
    trajectory_feedback_digest: Sha256Digest,
    config: TrajectoryAccountingConfigV1,
) -> TrajectoryConditionedReplayAccountingV1:
    """Build a strict additive product without changing raw feedback rows."""

    evaluations = trajectory_conditioned_evaluations(
        detections,
        representatives,
        replay,
        frequency_offsets_hz=frequency_offsets_hz,
        association_gate_hz=config.association_gate_hz,
    )
    accounting = summarize_trajectory_conditioned_replay(
        evaluations,
        detector_method=PilotMethod(config.detector_method),
        association_gate_hz=config.association_gate_hz,
        positive_margin=config.positive_margin,
    )
    return TrajectoryConditionedReplayAccountingV1(
        pilot_scan_digest=pilot_scan_digest,
        trajectory_bank_digest=trajectory_bank_digest,
        trajectory_feedback_digest=trajectory_feedback_digest,
        configuration_digest=config.digest,
        configuration=config,
        evaluation_count=len(accounting.evaluations),
        associated_evaluation_count=sum(
            item.baseline_margin is not None for item in accounting.evaluations
        ),
        unassociated_evaluation_count=sum(
            item.baseline_margin is None for item in accounting.evaluations
        ),
        evaluations=tuple(
            TrajectoryConditionedEvaluationV1(
                trajectory_id=item.trajectory_id,
                sample_start=item.sample_start,
                time_s=item.time_s,
                detector_method="glrt64",
                corrected_margin=item.corrected_margin,
                global_baseline_margin=item.global_baseline_margin,
                baseline_candidate_rank=item.baseline_candidate_rank,
                baseline_association_error_hz=item.baseline_association_error_hz,
                baseline_tracking_cfo_hz=item.baseline_tracking_cfo_hz,
                baseline_margin=item.baseline_margin,
            )
            for item in accounting.evaluations
        ),
        trajectories=tuple(
            TrajectoryReplaySummaryV1(
                trajectory_id=item.trajectory_id,
                evaluation_count=item.evaluation_count,
                associated_count=item.associated_count,
                unassociated_count=item.unassociated_count,
                unassociated_corrected_positive_count=(item.unassociated_corrected_positive_count),
                transitions=_transition_counts(item.transitions),
            )
            for item in accounting.trajectory_summaries
        ),
        associated_transitions=_transition_counts(accounting.associated_transitions),
        unique_probe_transitions=_transition_counts(accounting.unique_probe_transitions),
    )


def _finite_number(row: Mapping[str, Any], key: str) -> float:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"conditioned replay {key} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"conditioned replay {key} must be finite")
    return result


def _nonnegative_integer(row: Mapping[str, Any], key: str) -> int:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"conditioned replay {key} must be a nonnegative integer")
    return value


def _pair_counts(pairs: list[tuple[bool, bool]]) -> ReplayTransitionCountsV1:
    counts = Counter(pairs)
    return ReplayTransitionCountsV1(
        positive_to_positive=counts[(True, True)],
        positive_to_negative=counts[(True, False)],
        negative_to_positive=counts[(False, True)],
        negative_to_negative=counts[(False, False)],
    )


def build_trajectory_conditioned_accounting_v2(
    detections: tuple[PilotProbeDetection, ...],
    representatives: tuple[tuple[str, PolynomialTrajectory], ...],
    replay: tuple[Mapping[str, Any], ...],
    *,
    frequency_offsets_hz: Mapping[str, float],
    pilot_scan_digest: Sha256Digest,
    trajectory_bank_digest: Sha256Digest,
    trajectory_feedback_digest: Sha256Digest,
    config: TrajectoryAccountingConfigV2,
) -> TrajectoryConditionedReplayAccountingV2:
    """Build paired conditioned and independent-winner replay accounting."""

    selected_replay = tuple(row for row in replay if row.get("detector_method") == "glrt64")
    associated = trajectory_conditioned_evaluations(
        detections,
        representatives,
        selected_replay,
        frequency_offsets_hz=frequency_offsets_hz,
        association_gate_hz=config.association_gate_hz,
    )
    replay_by_identity = {
        (str(row.get("trajectory_id")), _nonnegative_integer(row, "sample_start")): row
        for row in selected_replay
    }
    if len(replay_by_identity) != len(selected_replay):
        raise ValueError("conditioned replay GLRT rows must be unique")
    evaluations = []
    for baseline_evaluation in associated:
        row = replay_by_identity[
            (baseline_evaluation.trajectory_id, baseline_evaluation.sample_start)
        ]
        is_associated = baseline_evaluation.baseline_margin is not None
        conditioned_margin = (
            _finite_number(row, "conditioned_corrected_margin") if is_associated else None
        )
        conditioned_tracking = (
            _finite_number(row, "conditioned_tracking_cfo_hz") if is_associated else None
        )
        conditioned_epoch = (
            _nonnegative_integer(row, "conditioned_epoch_sample") if is_associated else None
        )
        conditioned_seed = _finite_number(row, "conditioned_seed_cfo_hz") if is_associated else None
        evaluations.append(
            TrajectoryConditionedEvaluationV2(
                trajectory_id=baseline_evaluation.trajectory_id,
                sample_start=baseline_evaluation.sample_start,
                time_s=baseline_evaluation.time_s,
                detector_method="glrt64",
                reacquired_winner_margin=baseline_evaluation.corrected_margin,
                reacquired_winner_tracking_cfo_hz=_finite_number(row, "corrected_residual_cfo_hz"),
                conditioned_corrected_margin=conditioned_margin,
                conditioned_tracking_cfo_hz=conditioned_tracking,
                conditioned_epoch_sample=conditioned_epoch,
                conditioned_seed_cfo_hz=conditioned_seed,
                global_baseline_margin=baseline_evaluation.global_baseline_margin,
                baseline_candidate_rank=baseline_evaluation.baseline_candidate_rank,
                baseline_candidate_epoch_sample=(
                    baseline_evaluation.baseline_candidate_epoch_sample
                ),
                baseline_candidate_acquired_cfo_hz=(
                    baseline_evaluation.baseline_candidate_acquired_cfo_hz
                ),
                baseline_association_error_hz=(baseline_evaluation.baseline_association_error_hz),
                baseline_tracking_cfo_hz=baseline_evaluation.baseline_tracking_cfo_hz,
                baseline_margin=baseline_evaluation.baseline_margin,
            )
        )
    ordered = tuple(
        sorted(
            evaluations,
            key=lambda item: (item.trajectory_id, item.sample_start, item.detector_method),
        )
    )
    threshold = config.positive_margin
    matched = tuple(item for item in ordered if item.baseline_margin is not None)

    def associated_pairs(field: str) -> list[tuple[bool, bool]]:
        result = []
        for item in matched:
            corrected = getattr(item, field)
            if corrected is None:
                raise ValueError("matched conditioned replay row has no corrected score")
            assert item.baseline_margin is not None
            result.append((item.baseline_margin >= threshold, corrected >= threshold))
        return result

    by_trajectory: dict[str, list[TrajectoryConditionedEvaluationV2]] = defaultdict(list)
    by_sample: dict[int, list[TrajectoryConditionedEvaluationV2]] = defaultdict(list)
    for evaluation in ordered:
        by_trajectory[evaluation.trajectory_id].append(evaluation)
        by_sample[evaluation.sample_start].append(evaluation)
    trajectory_summaries = []
    for trajectory_id, rows in sorted(by_trajectory.items()):
        trajectory_matched = [item for item in rows if item.baseline_margin is not None]
        reacquired_pairs = []
        conditioned_pairs = []
        for evaluation in trajectory_matched:
            assert evaluation.baseline_margin is not None
            assert evaluation.conditioned_corrected_margin is not None
            baseline_positive = evaluation.baseline_margin >= threshold
            reacquired_pairs.append(
                (baseline_positive, evaluation.reacquired_winner_margin >= threshold)
            )
            conditioned_pairs.append(
                (baseline_positive, evaluation.conditioned_corrected_margin >= threshold)
            )
        unmatched = [item for item in rows if item.baseline_margin is None]
        trajectory_summaries.append(
            TrajectoryReplayComparisonSummaryV2(
                trajectory_id=trajectory_id,
                evaluation_count=len(rows),
                associated_count=len(trajectory_matched),
                unassociated_count=len(unmatched),
                unassociated_reacquired_positive_count=sum(
                    item.reacquired_winner_margin >= threshold for item in unmatched
                ),
                reacquired_transitions=_pair_counts(reacquired_pairs),
                conditioned_transitions=_pair_counts(conditioned_pairs),
            )
        )
    reacquired_unique_pairs = []
    conditioned_unique_pairs = []
    for rows in by_sample.values():
        global_margins = [
            item.global_baseline_margin for item in rows if item.global_baseline_margin is not None
        ]
        if not global_margins:
            continue
        baseline_positive = max(global_margins) >= threshold
        reacquired_unique_pairs.append(
            (baseline_positive, max(item.reacquired_winner_margin for item in rows) >= threshold)
        )
        conditioned_margins = [
            item.conditioned_corrected_margin
            for item in rows
            if item.conditioned_corrected_margin is not None
        ]
        conditioned_unique_pairs.append(
            (
                baseline_positive,
                bool(conditioned_margins) and max(conditioned_margins) >= threshold,
            )
        )
    return TrajectoryConditionedReplayAccountingV2(
        pilot_scan_digest=pilot_scan_digest,
        trajectory_bank_digest=trajectory_bank_digest,
        trajectory_feedback_digest=trajectory_feedback_digest,
        configuration_digest=config.digest,
        configuration=config,
        evaluation_count=len(ordered),
        associated_evaluation_count=len(matched),
        unassociated_evaluation_count=len(ordered) - len(matched),
        evaluations=ordered,
        trajectories=tuple(trajectory_summaries),
        reacquired_associated_transitions=_pair_counts(
            associated_pairs("reacquired_winner_margin")
        ),
        conditioned_associated_transitions=_pair_counts(
            associated_pairs("conditioned_corrected_margin")
        ),
        reacquired_unique_probe_transitions=_pair_counts(reacquired_unique_pairs),
        conditioned_unique_probe_transitions=_pair_counts(conditioned_unique_pairs),
    )


def render_trajectory_conditioned_accounting_png(
    documents: tuple[tuple[str, dict[str, Any]], ...],
    *,
    session_id: str,
) -> bytes:
    """Render correct component and physical-probe transition accounting."""

    if not documents or len(documents) > 4:
        raise ValueError("trajectory-accounting PNG requires one to four path documents")
    parsed = tuple(
        (label, TrajectoryConditionedReplayAccountingV1.model_validate(document))
        for label, document in documents
    )
    with _RENDER_LOCK:
        figure = Figure(
            figsize=(15.0, 4.8 * len(parsed)),
            dpi=160,
            constrained_layout=True,
        )
        FigureCanvasAgg(figure)
        axes = figure.subplots(len(parsed), 2, squeeze=False)
        colors = ("#009e73", "#d55e00", "#0072b2", "#8b949e")
        transition_labels = ("retained", "lost", "gained", "negative")
        for row, (label, document) in enumerate(parsed):
            transition_axis, trajectory_axis = axes[row]
            conditioned = document.associated_transitions
            unique = document.unique_probe_transitions
            transition_values = np.asarray(
                [
                    [
                        conditioned.positive_to_positive,
                        conditioned.positive_to_negative,
                        conditioned.negative_to_positive,
                        conditioned.negative_to_negative,
                    ],
                    [
                        unique.positive_to_positive,
                        unique.positive_to_negative,
                        unique.negative_to_positive,
                        unique.negative_to_negative,
                    ],
                ],
                dtype=float,
            )
            positions = np.arange(2)
            bottoms = np.zeros(2)
            for index, transition_label in enumerate(transition_labels):
                bars = transition_axis.bar(
                    positions,
                    transition_values[:, index],
                    bottom=bottoms,
                    color=colors[index],
                    width=0.62,
                    label=transition_label,
                )
                for bar, value, bottom in zip(
                    bars, transition_values[:, index], bottoms, strict=True
                ):
                    if value > 0:
                        transition_axis.text(
                            bar.get_x() + bar.get_width() / 2,
                            bottom + value / 2,
                            str(round(value)),
                            ha="center",
                            va="center",
                            fontsize=8,
                            color="white" if index != 3 else "black",
                        )
                bottoms += transition_values[:, index]
            transition_axis.set_xticks(positions, ("associated trajectory rows", "unique probes"))
            transition_axis.set_ylabel("Evaluation count")
            transition_axis.set_title(f"{label} · correct before/after transitions", loc="left")
            transition_axis.grid(axis="y", alpha=0.2)
            transition_axis.legend(loc="upper right", fontsize=8, ncols=2)

            trajectories = document.trajectories
            y = np.arange(len(trajectories))
            retained = np.asarray(
                [item.transitions.positive_to_positive for item in trajectories], dtype=float
            )
            lost = np.asarray(
                [item.transitions.positive_to_negative for item in trajectories], dtype=float
            )
            other = np.asarray(
                [
                    item.transitions.negative_to_positive + item.transitions.negative_to_negative
                    for item in trajectories
                ],
                dtype=float,
            )
            unmatched = np.asarray([item.unassociated_count for item in trajectories], dtype=float)
            left = np.zeros(len(trajectories))
            for values, color, item_label in (
                (retained, colors[0], "retained"),
                (lost, colors[1], "lost"),
                (other, colors[2], "matched baseline-negative"),
                (unmatched, colors[3], "unassociated"),
            ):
                trajectory_axis.barh(y, values, left=left, color=color, label=item_label)
                left += values
            trajectory_axis.set_yticks(
                y,
                tuple(item.trajectory_id.removeprefix("sha256:")[:8] for item in trajectories),
            )
            trajectory_axis.invert_yaxis()
            trajectory_axis.set_xlabel("Replay evaluation count")
            trajectory_axis.set_title(
                f"Per trajectory · {document.unassociated_evaluation_count} unmatched",
                loc="left",
            )
            trajectory_axis.grid(axis="x", alpha=0.2)
            trajectory_axis.legend(loc="lower right", fontsize=8)
        figure.suptitle(
            "Trajectory-conditioned GLRT64 replay accounting\n"
            "nearest same-component baseline · unmatched explicit · unique probes counted once\n"
            f"{session_id}",
            fontsize=12,
            fontweight="bold",
        )
        target = io.BytesIO()
        figure.savefig(
            target,
            format="png",
            dpi=160,
            facecolor="white",
            metadata={"Software": "leo-tracker trajectory-conditioned-replay-accounting-v1"},
        )
        return target.getvalue()


def _transition_values(value: ReplayTransitionCountsV1) -> tuple[int, int, int, int]:
    return (
        value.positive_to_positive,
        value.positive_to_negative,
        value.negative_to_positive,
        value.negative_to_negative,
    )


def render_trajectory_conditioned_accounting_v2_png(
    documents: tuple[tuple[str, dict[str, Any]], ...],
    *,
    session_id: str,
) -> bytes:
    """Render independent-winner versus transported-epoch replay performance."""

    if not documents or len(documents) > 4:
        raise ValueError("trajectory-accounting PNG requires one to four path documents")
    parsed = tuple(
        (label, TrajectoryConditionedReplayAccountingV2.model_validate(document))
        for label, document in documents
    )
    colors = ("#009e73", "#d55e00", "#0072b2", "#8b949e")
    transition_labels = ("retained", "lost", "gained", "negative")
    with _RENDER_LOCK:
        figure = Figure(
            figsize=(18.0, 4.8 * len(parsed)),
            dpi=160,
            constrained_layout=True,
        )
        FigureCanvasAgg(figure)
        axes = figure.subplots(len(parsed), 3, squeeze=False)
        for row_index, (label, document) in enumerate(parsed):
            associated_axis, unique_axis, trajectory_axis = axes[row_index]
            comparisons = (
                (
                    associated_axis,
                    f"{label} · associated trajectory rows",
                    document.reacquired_associated_transitions,
                    document.conditioned_associated_transitions,
                ),
                (
                    unique_axis,
                    "Unique physical probes",
                    document.reacquired_unique_probe_transitions,
                    document.conditioned_unique_probe_transitions,
                ),
            )
            for axis, title, reacquired, conditioned in comparisons:
                values = np.asarray(
                    [_transition_values(reacquired), _transition_values(conditioned)],
                    dtype=float,
                )
                positions = np.arange(2)
                bottoms = np.zeros(2)
                for index, transition_label in enumerate(transition_labels):
                    bars = axis.bar(
                        positions,
                        values[:, index],
                        bottom=bottoms,
                        color=colors[index],
                        width=0.62,
                        label=transition_label,
                    )
                    for bar, value, bottom in zip(bars, values[:, index], bottoms, strict=True):
                        if value > 0:
                            axis.text(
                                bar.get_x() + bar.get_width() / 2,
                                bottom + value / 2,
                                str(round(value)),
                                ha="center",
                                va="center",
                                fontsize=8,
                                color="white" if index != 3 else "black",
                            )
                    bottoms += values[:, index]
                axis.set_xticks(positions, ("independent winner", "transported epoch"))
                axis.set_ylabel("Evaluation count")
                axis.set_title(title, loc="left")
                axis.grid(axis="y", alpha=0.2)
                axis.legend(loc="upper right", fontsize=7, ncols=2)

            trajectories = document.trajectories
            positions = np.arange(len(trajectories))
            reacquired_lost = np.asarray(
                [item.reacquired_transitions.positive_to_negative for item in trajectories],
                dtype=float,
            )
            conditioned_lost = np.asarray(
                [item.conditioned_transitions.positive_to_negative for item in trajectories],
                dtype=float,
            )
            height = 0.36
            trajectory_axis.barh(
                positions - height / 2,
                reacquired_lost,
                height=height,
                color=colors[1],
                label="independent-winner lost",
            )
            trajectory_axis.barh(
                positions + height / 2,
                conditioned_lost,
                height=height,
                color=colors[0],
                label="transported-epoch lost",
            )
            trajectory_axis.set_yticks(
                positions,
                tuple(item.trajectory_id.removeprefix("sha256:")[:8] for item in trajectories),
            )
            trajectory_axis.invert_yaxis()
            trajectory_axis.set_xlabel("Positive → negative row count")
            trajectory_axis.set_title(
                f"Per trajectory · {document.unassociated_evaluation_count} unmatched",
                loc="left",
            )
            trajectory_axis.grid(axis="x", alpha=0.2)
            trajectory_axis.legend(loc="lower right", fontsize=7)
        figure.suptitle(
            "Trajectory-corrected GLRT64: independent reacquisition vs paired replay\n"
            "same associated candidate · transported epoch · signed residual-CFO seed\n"
            f"{session_id}",
            fontsize=12,
            fontweight="bold",
        )
        target = io.BytesIO()
        figure.savefig(
            target,
            format="png",
            dpi=160,
            facecolor="white",
            metadata={"Software": "leo-tracker trajectory-conditioned-replay-accounting-v2"},
        )
        return target.getvalue()
