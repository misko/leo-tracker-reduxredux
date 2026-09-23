import numpy as np
import pytest

from leo.analysis.research.candidate_phase_validation import (
    CandidatePhaseEvidence,
    score_candidate_integrated_phase,
    seeded_group_split,
)


def _evidence(measured, predictions, *, endpoints=None):
    if endpoints is None:
        endpoints = [(2 * index, 2 * index + 1) for index in range(6)]
    return CandidatePhaseEvidence(
        measured_phase_advance_rad=np.asarray(measured),
        interval_duration_s=np.asarray([0.001, 0.002, 0.001, 0.002, 0.001, 0.002]),
        group_id=np.asarray(["a", "a", "b", "b", "c", "d"]),
        training_group_ids=("a", "c"),
        candidate_integrated_phase_rad=np.asarray(predictions),
        candidate_ids=("candidate-a", "candidate-b"),
        split_seed=73,
        endpoint_frame_ids=np.asarray(endpoints),
    )


def test_constant_cfo_difference_is_removed_by_locklet_bias():
    duration = np.asarray([0.001, 0.002, 0.001, 0.002, 0.001, 0.002])
    first = np.linspace(0.0, 0.4, 6)
    second = first + 2 * np.pi * 40.0 * duration
    measured = first + 2 * np.pi * 25.0 * duration

    result = score_candidate_integrated_phase(_evidence(measured, [first, second]))

    assert result.heldout_composite_score[0] == pytest.approx(
        result.heldout_composite_score[1], abs=2e-4
    )
    assert result.maximum_candidate_contrast_rad < 0.002
    assert not result.identifiable_after_nuisance


def test_time_varying_candidate_shape_wins_held_groups():
    correct = np.asarray([0.02, 0.09, 0.18, 0.34, 0.55, 0.81])
    wrong = np.asarray([0.02, 0.09, -0.20, -0.33, -0.52, -0.78])
    duration = np.asarray([0.001, 0.002, 0.001, 0.002, 0.001, 0.002])
    measured = correct + 2 * np.pi * 31.0 * duration

    result = score_candidate_integrated_phase(_evidence(measured, [correct, wrong]))

    assert result.heldout_composite_score[0] > result.heldout_composite_score[1] + 0.5
    assert result.identifiable_after_nuisance


def test_held_mutation_never_changes_training_fitted_nuisance():
    correct = np.asarray([0.02, 0.09, 0.18, 0.34, 0.55, 0.81])
    wrong = -correct
    baseline = correct + 0.1
    mutated = baseline.copy()
    mutated[[2, 3, 5]] += 1.1  # held groups b and d only

    first = score_candidate_integrated_phase(_evidence(baseline, [correct, wrong]))
    second = score_candidate_integrated_phase(_evidence(mutated, [correct, wrong]))

    np.testing.assert_array_equal(first.fitted_bias_hz, second.fitted_bias_hz)
    assert not np.allclose(first.heldout_composite_score, second.heldout_composite_score)


def test_shared_frame_endpoint_across_split_is_rejected():
    endpoints = [(0, 1), (2, 3), (1, 5), (6, 7), (8, 9), (10, 11)]
    evidence = _evidence(np.zeros(6), np.zeros((2, 6)), endpoints=endpoints)

    with pytest.raises(ValueError, match="frame endpoint"):
        score_candidate_integrated_phase(evidence)


def test_shared_frame_endpoint_across_groups_is_rejected_within_partition():
    endpoints = [(0, 1), (2, 3), (4, 5), (6, 7), (8, 9), (8, 11)]
    evidence = _evidence(np.zeros(6), np.zeros((2, 6)), endpoints=endpoints)

    with pytest.raises(ValueError, match="different phase groups"):
        score_candidate_integrated_phase(evidence)


def test_seeded_split_is_reproducible_and_not_chronological():
    groups = tuple(range(10))
    first = seeded_group_split(groups, seed=91)
    second = seeded_group_split(groups, seed=91)

    assert first == second
    assert set(first[0]).isdisjoint(first[1])
    assert first[1] != groups[-len(first[1]) :]
