"""Build and render derived trajectory-conditioned replay accounting."""

from __future__ import annotations

import io
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
    TrajectoryConditionedEvaluationV1,
    TrajectoryConditionedReplayAccountingV1,
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
                unassociated_corrected_positive_count=(
                    item.unassociated_corrected_positive_count
                ),
                transitions=_transition_counts(item.transitions),
            )
            for item in accounting.trajectory_summaries
        ),
        associated_transitions=_transition_counts(accounting.associated_transitions),
        unique_probe_transitions=_transition_counts(accounting.unique_probe_transitions),
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
                    item.transitions.negative_to_positive
                    + item.transitions.negative_to_negative
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
