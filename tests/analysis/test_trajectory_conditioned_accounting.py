from __future__ import annotations

import pytest

from leo.analysis.starlink.acquisition import NumericalStatus
from leo.analysis.starlink.pilot_methods import (
    PilotMethod,
    PilotMethodCandidate,
    PilotMethodScore,
    PilotProbeDetection,
)
from leo.analysis.starlink.trajectories import PolynomialTrajectory
from leo.analysis.starlink.trajectory_accounting import (
    associate_trajectory_baseline,
    summarize_trajectory_conditioned_replay,
    trajectory_conditioned_evaluations,
)


def _score(cfo_hz: float, margin: float) -> PilotMethodScore:
    return PilotMethodScore(
        PilotMethod.GLRT64,
        margin + 0.04,
        0.04,
        margin,
        0.0,
        cfo_hz,
    )


def _candidate(rank: int, cfo_hz: float, margin: float) -> PilotMethodCandidate:
    return PilotMethodCandidate(rank, rank, cfo_hz, (_score(cfo_hz, margin),), None, None)


def _detection(
    sample_start: int,
    *candidates: PilotMethodCandidate,
) -> PilotProbeDetection:
    primary = candidates[0]
    return PilotProbeDetection(
        NumericalStatus.COMPLETE,
        sample_start,
        sample_start / 100.0,
        primary.local_epoch_sample,
        primary.acquired_cfo_hz,
        primary.scores,
        None,
        None,
        "fixture",
        source_candidate_count=len(candidates),
        candidates=tuple(candidates),
    )


def _trajectory(trajectory_id: str, cfo_hz: float) -> PolynomialTrajectory:
    return PolynomialTrajectory(
        trajectory_id,
        PilotMethod.GLRT64,
        1,
        0.0,
        (0.0, cfo_hz),
        0.0,
        1.0,
        (f"{trajectory_id}-a", f"{trajectory_id}-b"),
        2,
        0.0,
        0.0,
        0.0,
        0,
    )


def _row(trajectory_id: str, sample_start: int, corrected_margin: float) -> dict:
    return {
        "trajectory_id": trajectory_id,
        "sample_start": sample_start,
        "time_s": sample_start / 100.0,
        "detector_method": "glrt64",
        "corrected_margin": corrected_margin,
    }


def test_secondary_candidate_is_selected_instead_of_the_global_winner() -> None:
    detection = _detection(
        0,
        _candidate(0, -240_000.0, 0.40),
        _candidate(1, -130_250.0, 0.31),
    )

    matched = associate_trajectory_baseline(
        detection,
        _trajectory("secondary", 97_000.0),
        frequency_offset_hz=-227_272.72727272726,
        association_gate_hz=2_500.0,
    )

    assert matched is not None
    assert matched.candidate_rank == 1
    assert matched.trajectory_tracking_cfo_hz == -130_250.0
    assert matched.association_error_hz == pytest.approx(22.727272727264557)


def test_unrelated_global_winner_remains_explicitly_unassociated() -> None:
    detection = _detection(0, _candidate(0, -240_000.0, 0.40))

    matched = associate_trajectory_baseline(
        detection,
        _trajectory("secondary", -130_000.0),
        frequency_offset_hz=0.0,
        association_gate_hz=2_500.0,
    )

    assert matched is None


def test_overlapping_trajectories_bind_independently_and_unique_probes_use_best_replay() -> None:
    detections = (
        _detection(
            0,
            _candidate(0, -240_000.0, 0.40),
            _candidate(1, -130_000.0, 0.30),
        ),
        _detection(10, _candidate(0, -240_000.0, 0.42)),
    )
    primary = _trajectory("primary", -240_000.0)
    secondary = _trajectory("secondary", -130_000.0)
    replay = (
        _row("primary", 0, 0.41),
        _row("secondary", 0, 0.32),
        _row("primary", 10, 0.43),
        _row("secondary", 10, 0.01),
    )

    evaluations = trajectory_conditioned_evaluations(
        detections,
        (("family-primary", primary), ("family-secondary", secondary)),
        replay,
        frequency_offsets_hz={"primary": 0.0, "secondary": 0.0},
        association_gate_hz=2_500.0,
    )
    accounting = summarize_trajectory_conditioned_replay(
        evaluations,
        association_gate_hz=2_500.0,
    )

    by_identity = {(item.trajectory_id, item.sample_start): item for item in evaluations}
    assert by_identity[("primary", 0)].baseline_candidate_rank == 0
    assert by_identity[("secondary", 0)].baseline_candidate_rank == 1
    assert by_identity[("secondary", 10)].baseline_margin is None
    assert accounting.associated_transitions.positive_to_positive == 3
    assert accounting.associated_transitions.positive_to_negative == 0
    assert accounting.unique_probe_transitions.positive_to_positive == 2
    secondary_summary = next(
        item for item in accounting.trajectory_summaries if item.trajectory_id == "secondary"
    )
    assert secondary_summary.associated_count == 1
    assert secondary_summary.unassociated_count == 1
    assert secondary_summary.unassociated_corrected_positive_count == 0


def test_non_string_replay_detector_method_is_rejected() -> None:
    detection = _detection(0, _candidate(0, -240_000.0, 0.40))
    trajectory = _trajectory("primary", -240_000.0)
    row = _row("primary", 0, 0.41)
    row["detector_method"] = None

    with pytest.raises(ValueError, match="detector method is invalid"):
        trajectory_conditioned_evaluations(
            (detection,),
            (("family-primary", trajectory),),
            (row,),
            frequency_offsets_hz={"primary": 0.0},
            association_gate_hz=2_500.0,
        )
