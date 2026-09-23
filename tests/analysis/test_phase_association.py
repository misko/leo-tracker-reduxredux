import numpy as np
import pytest

from leo.analysis.research.phase_association import (
    HeldoutPhaseLinkEvidence,
    PhaseAssociationHypothesis,
    RandomGroupSplit,
    score_phase_association_hypotheses,
    score_phase_link,
    seeded_random_group_split,
)


def _evidence(exact, control):
    return HeldoutPhaseLinkEvidence(
        link_id="rx0-rx1-visit-7",
        split=RandomGroupSplit(19, ("g0", "g2"), ("g1", "g3", "g4")),
        residual_phase_rad=np.asarray(exact),
        residual_group_id=np.asarray(["g1", "g3", "g4"]),
        wrong_pair_phase_rad=np.asarray(control),
        wrong_pair_group_id=np.asarray(["g1", "g3", "g4"]),
    )


def test_seeded_split_is_random_reproducible_and_keeps_whole_groups():
    groups = tuple(f"g{index}" for index in range(12))
    first = seeded_random_group_split(groups, seed=8021)
    second = seeded_random_group_split(groups, seed=8021)

    assert first == second
    assert set(first.training_group_ids).isdisjoint(first.heldout_group_ids)
    assert set(first.training_group_ids) | set(first.heldout_group_ids) == set(groups)
    assert first.heldout_group_ids != groups[-len(first.heldout_group_ids) :]


def test_supported_phase_link_reweights_only_hypotheses_asserting_that_link():
    evidence = _evidence([0.02, -0.03, 0.01], [0.0, 2.1, -2.1])
    hypotheses = (
        PhaseAssociationHypothesis("linked-a", frozenset({evidence.link_id})),
        PhaseAssociationHypothesis("linked-b", frozenset({evidence.link_id})),
        PhaseAssociationHypothesis("separate", frozenset()),
    )
    result = score_phase_association_hypotheses(hypotheses, (evidence,))

    assert result.links[0].state == "supported"
    assert result.normalized_conditional_weight[0] == pytest.approx(
        result.normalized_conditional_weight[1]
    )
    assert result.normalized_conditional_weight[0] > result.normalized_conditional_weight[2]
    assert result.phase_log_factor[0] == pytest.approx(result.phase_log_factor[1])
    serialized = result.as_serializable()
    assert serialized["links"][0]["split_seed"] == 19
    assert serialized["links"][0]["heldout_group_ids"] == ["g1", "g3", "g4"]


def test_wrong_pair_gate_abstains_instead_of_creating_association_evidence():
    score = score_phase_link(_evidence([0.0, 0.1, -0.1], [0.0, 0.1, -0.1]))

    assert score.state == "abstained"
    assert score.conditional_composite_log_factor == 0.0


def test_residuals_cannot_include_training_or_omit_heldout_groups():
    evidence = _evidence([0.0, 0.1, -0.1], [0.0, 2.1, -2.1])
    contaminated = HeldoutPhaseLinkEvidence(
        link_id=evidence.link_id,
        split=evidence.split,
        residual_phase_rad=np.append(evidence.residual_phase_rad, 0.0),
        residual_group_id=np.append(evidence.residual_group_id, "g0"),
        wrong_pair_phase_rad=evidence.wrong_pair_phase_rad,
        wrong_pair_group_id=evidence.wrong_pair_group_id,
    )

    with pytest.raises(ValueError, match="exactly cover held-out"):
        score_phase_link(contaminated)


def test_samples_within_one_group_do_not_inflate_the_log_factor():
    single = _evidence([0.0, 0.1, -0.1], [0.0, 2.1, -2.1])
    repeated = HeldoutPhaseLinkEvidence(
        link_id=single.link_id,
        split=single.split,
        residual_phase_rad=np.repeat(single.residual_phase_rad, 20),
        residual_group_id=np.repeat(single.residual_group_id, 20),
        wrong_pair_phase_rad=np.repeat(single.wrong_pair_phase_rad, 20),
        wrong_pair_group_id=np.repeat(single.wrong_pair_group_id, 20),
    )

    assert score_phase_link(single).conditional_composite_log_factor == pytest.approx(
        score_phase_link(repeated).conditional_composite_log_factor
    )


def test_uniform_samples_inside_groups_cannot_be_normalized_into_phase_support():
    phases = np.tile([0.0, np.pi / 2, np.pi, -np.pi / 2], 3)
    groups = np.repeat(["g1", "g3", "g4"], 4)
    evidence = HeldoutPhaseLinkEvidence(
        link_id="noise",
        split=RandomGroupSplit(19, ("g0", "g2"), ("g1", "g3", "g4")),
        residual_phase_rad=phases,
        residual_group_id=groups,
        wrong_pair_phase_rad=phases,
        wrong_pair_group_id=groups,
    )

    score = score_phase_link(evidence)
    assert score.state == "abstained"
    assert score.exact_phase_resultant < 1e-12
    assert score.conditional_composite_log_factor == 0.0


def test_split_rejects_chronological_or_overlapping_provenance():
    overlap = HeldoutPhaseLinkEvidence(
        link_id="bad",
        split=RandomGroupSplit(5, ("a", "b"), ("b", "c")),
        residual_phase_rad=np.asarray([0.0, 0.0]),
        residual_group_id=np.asarray(["b", "c"]),
        wrong_pair_phase_rad=np.asarray([0.0, 1.0]),
        wrong_pair_group_id=np.asarray(["b", "c"]),
    )
    with pytest.raises(ValueError, match="disjoint"):
        score_phase_link(overlap)
