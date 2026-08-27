from __future__ import annotations

import math
from dataclasses import replace

import pytest

from leo.analysis.research.long_arc_hypothesis_closure import (
    LongArcChronologicalScoreBlock,
    LongArcHypothesisBlockLogScore,
    LongArcHypothesisClosureConfig,
    LongArcHypothesisClosureInputError,
    LongArcHypothesisClosureWorkLimitError,
    LongArcHypothesisPrior,
    close_long_arc_hypotheses,
    observation_inventory_digest,
    seal_chronological_score_block,
    seal_long_arc_hypothesis_closure_evidence,
    verify_long_arc_hypothesis_closure_result,
)
from leo.contracts.digests import canonical_digest


def _digest(label: str) -> str:
    return canonical_digest({"test": label})


def _prior(
    label: str,
    *,
    family: str,
    probability: float,
    connected_neighborhood: str,
    catalog_numbers: tuple[int, ...] = (),
    tau_s: tuple[float, ...] = (),
) -> LongArcHypothesisPrior:
    return LongArcHypothesisPrior(
        hypothesis_id=_digest(f"hypothesis:{label}"),
        family=family,  # type: ignore[arg-type]
        normalized_log_prior_probability=math.log(probability),
        connected_neighborhood_label=connected_neighborhood,
        catalog_numbers=catalog_numbers,
        tau_s=tau_s,
        nuisance_model_reference_digest=_digest(f"nuisance-model:{label}"),
        change_point_model_reference_digest=(
            _digest(f"change-point-model:{label}") if family == "h1-switch" else None
        ),
    )


def _basic_hypotheses(
    *,
    include_optional: bool = False,
    outside_mass: float = 0.0,
) -> tuple[LongArcHypothesisPrior, ...]:
    if include_optional:
        return (
            _prior(
                "null",
                family="h0-radio-null",
                probability=0.10,
                connected_neighborhood="radio-null",
            ),
            _prior(
                "a-minus",
                family="h1-single-candidate",
                probability=0.20,
                connected_neighborhood="rf-class-a",
                catalog_numbers=(65438,),
                tau_s=(-0.25,),
            ),
            _prior(
                "a-plus",
                family="h1-single-candidate",
                probability=0.15,
                connected_neighborhood="rf-class-a",
                catalog_numbers=(65438,),
                tau_s=(0.25,),
            ),
            _prior(
                "b",
                family="h1-single-candidate",
                probability=0.15,
                connected_neighborhood="rf-class-b",
                catalog_numbers=(59748,),
                tau_s=(0.0,),
            ),
            _prior(
                "a-to-b",
                family="h1-switch",
                probability=0.20,
                connected_neighborhood="switch-a-b",
                catalog_numbers=(65438, 59748),
                tau_s=(0.0, 0.0),
            ),
            _prior(
                "a-plus-b",
                family="k2-two-candidate",
                probability=0.20,
                connected_neighborhood="simultaneous-a-b",
                catalog_numbers=(59748, 65438),
                tau_s=(0.0, 0.0),
            ),
        )
    remaining = 1.0 - outside_mass
    return (
        _prior(
            "null",
            family="h0-radio-null",
            probability=0.10,
            connected_neighborhood="radio-null",
        ),
        _prior(
            "a",
            family="h1-single-candidate",
            probability=(remaining - 0.10) / 2.0,
            connected_neighborhood="rf-class-a",
            catalog_numbers=(65438,),
            tau_s=(0.0,),
        ),
        _prior(
            "b",
            family="h1-single-candidate",
            probability=(remaining - 0.10) / 2.0,
            connected_neighborhood="rf-class-b",
            catalog_numbers=(59748,),
            tau_s=(0.0,),
        ),
    )


def _block(
    index: int,
    hypotheses: tuple[LongArcHypothesisPrior, ...],
    log_scores: tuple[float, ...],
    preceding: tuple[LongArcChronologicalScoreBlock, ...],
) -> LongArcChronologicalScoreBlock:
    assert len(hypotheses) == len(log_scores)
    block_id = _digest(f"block:{index}")
    start = 1_800_000_000_000_000_000 + index * 1_000_000_000
    end = start + 1_000_000_000
    observations = (
        _digest(f"observation:{index}:0"),
        _digest(f"observation:{index}:1"),
    )
    inventory = observation_inventory_digest(
        block_id=block_id,
        block_start_utc_ns=start,
        block_end_utc_ns=end,
        observation_ids=observations,
    )
    scores = tuple(
        LongArcHypothesisBlockLogScore(
            hypothesis_id=hypothesis.hypothesis_id,
            proper_log_score=log_score,
            score_reference_digest=_digest(f"score:{index}:{state_index}:{log_score}"),
            scored_observation_inventory_digest=inventory,
            nuisance_state_reference_digest=_digest(f"nuisance-state:{index}:{state_index}"),
            change_point_reference_digest=(
                _digest(f"change-point:{index}:{state_index}")
                if hypothesis.family == "h1-switch"
                else None
            ),
        )
        for state_index, (hypothesis, log_score) in enumerate(
            zip(hypotheses, log_scores, strict=True)
        )
    )
    return seal_chronological_score_block(
        block_id=block_id,
        block_start_utc_ns=start,
        block_end_utc_ns=end,
        observation_ids=observations,
        scores=scores,
        preceding_blocks=preceding,
    )


def _evidence(
    hypotheses: tuple[LongArcHypothesisPrior, ...],
    score_rows: tuple[tuple[float, ...], ...],
    *,
    pruned_prior_mass: float = 0.0,
    unresolved_prior_mass: float = 0.0,
    development_limitations: tuple[str, ...] = (),
):
    blocks: list[LongArcChronologicalScoreBlock] = []
    for index, scores in enumerate(score_rows):
        blocks.append(_block(index, hypotheses, scores, tuple(blocks)))
    return seal_long_arc_hypothesis_closure_evidence(
        sequence_label="synthetic-long-arc",
        graph_content_digest=_digest("graph"),
        scoring_protocol_digest=_digest("scoring-protocol"),
        prior_policy_digest=_digest("prior-policy"),
        connected_neighborhood_map_digest=_digest("response-free-connected-neighborhood-map"),
        hypotheses=hypotheses,
        blocks=tuple(blocks),
        pruned_prior_mass=pruned_prior_mass,
        unresolved_prior_mass=unresolved_prior_mass,
        development_limitations=development_limitations,  # type: ignore[arg-type]
    )


def test_accumulates_family_and_response_free_neighborhood_mass_without_identity_claim() -> None:
    hypotheses = _basic_hypotheses(include_optional=True)
    evidence = _evidence(
        hypotheses,
        (
            (-5.0, 0.0, -0.1, -4.0, -4.0, -4.0),
            (-5.0, 0.0, -0.1, -4.0, -4.0, -4.0),
            (-5.0, 0.0, -0.1, -4.0, -4.0, -4.0),
        ),
    )

    result = close_long_arc_hypotheses(evidence)

    assert len(result.rolling_summaries) == 3
    assert result.final_summary == result.rolling_summaries[-1]
    assert result.final_summary.outcome is not None
    assert result.final_summary.outcome.outcome == "singleton"
    assert (
        result.final_summary.outcome.reason
        == "single-catalogue-connected-neighborhood-meets-policy"
    )
    neighborhood_a = next(
        item
        for item in result.final_summary.connected_neighborhood_posterior
        if item.connected_neighborhood_label == "rf-class-a"
    )
    assert neighborhood_a.evaluated_state_count == 2
    assert neighborhood_a.within_candidate_probability is not None
    assert neighborhood_a.within_candidate_probability > 0.99
    assert sum(
        item.posterior_probability for item in result.final_summary.family_posterior
    ) == pytest.approx(1.0)
    assert sum(
        item.posterior_probability for item in result.final_summary.connected_neighborhood_posterior
    ) == pytest.approx(1.0)
    assert result.final_summary.candidate_connected_neighborhood_entropy_nats is not None
    assert result.final_summary.effective_candidate_connected_neighborhood_count is not None
    assert result.final_summary.effective_candidate_connected_neighborhood_count >= 1.0
    for prefix in result.rolling_summaries[:-1]:
        assert prefix.connected_neighborhood_summary_status == "suppressed-final-prefix-map"
        assert prefix.connected_neighborhood_posterior == ()
        assert prefix.connected_neighborhood_entropy_nats is None
        assert prefix.candidate_connected_neighborhood_entropy_nats is None
        assert prefix.effective_candidate_connected_neighborhood_count is None
        assert prefix.outcome is None
    assert result.final_summary.connected_neighborhood_summary_status == "available-final-prefix"
    assert tuple(item.status for item in result.optional_family_availability) == (
        "evaluated",
        "evaluated",
    )
    assert result.change_point_model_reference_digests
    assert result.change_point_reference_digests
    assert result.posterior_conditioned_on_evaluated_states
    assert result.outside_prior_mass_updated is False
    assert result.candidate_selection_performed is False
    assert result.rf_response_accessed is False
    assert result.likelihood_fitted is False
    assert result.posterior_probability_calibrated is False
    assert result.model_selection_gate_produced is False
    assert result.outcome_is_descriptive
    assert result.identity_claimed is False
    verify_long_arc_hypothesis_closure_result(result)


def test_equal_candidate_neighborhoods_report_ambiguity_and_absent_optional_families() -> None:
    hypotheses = _basic_hypotheses()
    result = close_long_arc_hypotheses(_evidence(hypotheses, ((-8.0, 0.0, 0.0), (-8.0, 0.0, 0.0))))

    assert result.final_summary.outcome is not None
    assert result.final_summary.outcome.outcome == "ambiguity"
    assert result.final_summary.outcome.reason == "multiple-connected-neighborhoods-required"
    assert len(result.final_summary.outcome.credible_connected_neighborhoods) == 2
    assert tuple(item.status for item in result.optional_family_availability) == (
        "structurally-inapplicable",
        "structurally-inapplicable",
    )
    assert all(item.evaluated_state_count == 0 for item in result.optional_family_availability)


def test_one_high_mass_multi_norad_connected_neighborhood_is_not_a_singleton() -> None:
    hypotheses = (
        _prior(
            "null",
            family="h0-radio-null",
            probability=0.10,
            connected_neighborhood="radio-null",
        ),
        _prior(
            "a",
            family="h1-single-candidate",
            probability=0.45,
            connected_neighborhood="unresolved-pair",
            catalog_numbers=(65438,),
            tau_s=(0.0,),
        ),
        _prior(
            "b",
            family="h1-single-candidate",
            probability=0.45,
            connected_neighborhood="unresolved-pair",
            catalog_numbers=(59748,),
            tau_s=(0.0,),
        ),
    )

    result = close_long_arc_hypotheses(_evidence(hypotheses, ((-10.0, 0.0, 0.0),)))

    candidate_neighborhood = next(
        item
        for item in result.final_summary.connected_neighborhood_posterior
        if item.connected_neighborhood_label == "unresolved-pair"
    )
    assert candidate_neighborhood.catalog_numbers == (59748, 65438)
    assert candidate_neighborhood.evaluated_state_count == 2
    assert candidate_neighborhood.within_candidate_probability == pytest.approx(1.0)
    assert result.final_summary.outcome is not None
    assert result.final_summary.outcome.outcome == "ambiguity"
    assert result.final_summary.outcome.reason == (
        "connected-neighborhood-contains-multiple-catalogues"
    )


@pytest.mark.parametrize(
    ("score_rows", "outside", "expected_reason"),
    (
        (((5.0, 0.0, 0.0),), 0.0, "radio-or-unassigned-competitive"),
        (((-8.0, 8.0, -8.0),), 0.10, "outside-evaluated-prior-mass"),
    ),
)
def test_radio_or_unassigned_or_unevaluated_mass_forces_unresolved(
    score_rows: tuple[tuple[float, ...], ...],
    outside: float,
    expected_reason: str,
) -> None:
    hypotheses = _basic_hypotheses(outside_mass=outside)
    result = close_long_arc_hypotheses(
        _evidence(
            hypotheses,
            score_rows,
            pruned_prior_mass=outside / 2.0,
            unresolved_prior_mass=outside / 2.0,
        )
    )

    outcome = result.final_summary.outcome
    assert outcome is not None
    assert outcome.outcome == "unresolved"
    assert outcome.reason == expected_reason
    assert outcome.candidate_posterior_probability + (
        outcome.h0_radio_or_unassigned_posterior_probability
    ) == pytest.approx(1.0)
    assert outcome.minimum_candidate_posterior_probability == 0.5
    assert not hasattr(outcome, "null_posterior_probability")
    accounting = result.prior_mass_accounting
    assert accounting.evaluated_prior_mass == pytest.approx(1.0 - outside)
    assert accounting.h0_radio_or_unassigned_prior_mass == pytest.approx(0.1)
    assert accounting.evaluated_candidate_prior_mass == pytest.approx(0.9 - outside)
    assert accounting.outside_evaluated_prior_mass == pytest.approx(outside)
    assert accounting.accounted_prior_mass == pytest.approx(1.0)
    assert accounting.h0_radio_or_unassigned_is_subset_of_evaluated


def test_priors_must_be_normalized_with_pruned_and_unresolved_mass() -> None:
    hypotheses = _basic_hypotheses(outside_mass=0.1)
    evidence = _evidence(hypotheses, ((0.0, 0.0, 0.0),))

    with pytest.raises(LongArcHypothesisClosureInputError, match="must sum to one"):
        close_long_arc_hypotheses(evidence)


def test_incomplete_opportunity_inventory_forces_descriptive_unresolved_outcome() -> None:
    hypotheses = _basic_hypotheses()
    result = close_long_arc_hypotheses(
        _evidence(
            hypotheses,
            ((-20.0, 20.0, -20.0),),
            development_limitations=("incomplete-opportunity-inventory",),
        )
    )

    assert result.development_limitations == ("incomplete-opportunity-inventory",)
    assert result.final_summary.outcome is not None
    assert result.final_summary.outcome.outcome == "unresolved"
    assert result.final_summary.outcome.reason == "incomplete-opportunity-inventory"


def test_every_block_requires_the_exact_common_hypothesis_inventory() -> None:
    hypotheses = _basic_hypotheses()
    good = _block(0, hypotheses, (0.0, 0.0, 0.0), ())
    block_id = _digest("block:1")
    start = good.block_end_utc_ns
    end = start + 1_000_000_000
    observations = (_digest("missing-score-observation"),)
    inventory = observation_inventory_digest(
        block_id=block_id,
        block_start_utc_ns=start,
        block_end_utc_ns=end,
        observation_ids=observations,
    )
    scores = tuple(
        LongArcHypothesisBlockLogScore(
            hypothesis_id=item.hypothesis_id,
            proper_log_score=0.0,
            score_reference_digest=_digest(f"missing-score:{index}"),
            scored_observation_inventory_digest=inventory,
            nuisance_state_reference_digest=_digest(f"missing-nuisance:{index}"),
        )
        for index, item in enumerate(hypotheses[:-1])
    )
    incomplete = seal_chronological_score_block(
        block_id=block_id,
        block_start_utc_ns=start,
        block_end_utc_ns=end,
        observation_ids=observations,
        scores=scores,
        preceding_blocks=(good,),
    )
    evidence = seal_long_arc_hypothesis_closure_evidence(
        sequence_label="incomplete",
        graph_content_digest=_digest("graph"),
        scoring_protocol_digest=_digest("protocol"),
        prior_policy_digest=_digest("prior"),
        connected_neighborhood_map_digest=_digest("neighborhoods"),
        hypotheses=hypotheses,
        blocks=(good, incomplete),
    )

    with pytest.raises(LongArcHypothesisClosureInputError, match="exact ordered"):
        close_long_arc_hypotheses(evidence)


def test_conditioning_history_must_contain_all_and_only_preceding_blocks() -> None:
    hypotheses = _basic_hypotheses()
    first = _block(0, hypotheses, (0.0, 0.0, 0.0), ())
    noncausal_second = _block(1, hypotheses, (0.0, 0.0, 0.0), ())
    evidence = seal_long_arc_hypothesis_closure_evidence(
        sequence_label="noncausal",
        graph_content_digest=_digest("graph"),
        scoring_protocol_digest=_digest("protocol"),
        prior_policy_digest=_digest("prior"),
        connected_neighborhood_map_digest=_digest("neighborhoods"),
        hypotheses=hypotheses,
        blocks=(first, noncausal_second),
    )

    with pytest.raises(LongArcHypothesisClosureInputError, match="non-causal"):
        close_long_arc_hypotheses(evidence)


def test_digest_closure_rejects_score_mutation_and_result_mutation() -> None:
    hypotheses = _basic_hypotheses()
    evidence = _evidence(hypotheses, ((0.0, 0.0, 0.0),))
    score = evidence.blocks[0].scores[0]
    changed_score = replace(score, proper_log_score=score.proper_log_score + 1.0)
    changed_block = replace(
        evidence.blocks[0],
        scores=(changed_score, *evidence.blocks[0].scores[1:]),
    )
    changed_evidence = replace(evidence, blocks=(changed_block,))

    with pytest.raises(LongArcHypothesisClosureInputError, match="block digest differs"):
        close_long_arc_hypotheses(changed_evidence)

    result = close_long_arc_hypotheses(evidence)
    with pytest.raises(LongArcHypothesisClosureInputError, match="result digest differs"):
        verify_long_arc_hypothesis_closure_result(
            replace(result, sequence_label="mutated-after-result")
        )


def test_changing_a_future_score_cannot_rewrite_earlier_prefix_summaries() -> None:
    hypotheses = _basic_hypotheses()
    original = _evidence(
        hypotheses,
        ((-3.0, 0.0, -1.0), (-3.0, 0.0, -1.0), (-3.0, 0.0, -1.0)),
    )
    original_result = close_long_arc_hypotheses(original)
    prefix = original.blocks[:2]
    changed_last = _block(2, hypotheses, (-3.0, -20.0, 20.0), prefix)
    changed = seal_long_arc_hypothesis_closure_evidence(
        sequence_label=original.sequence_label,
        graph_content_digest=original.graph_content_digest,
        scoring_protocol_digest=original.scoring_protocol_digest,
        prior_policy_digest=original.prior_policy_digest,
        connected_neighborhood_map_digest=original.connected_neighborhood_map_digest,
        hypotheses=hypotheses,
        blocks=(*prefix, changed_last),
    )
    changed_result = close_long_arc_hypotheses(changed)

    assert changed_result.rolling_summaries[:2] == original_result.rolling_summaries[:2]
    assert changed_result.final_summary != original_result.final_summary
    assert changed_result.future_blocks_rewrite_prior_summaries is False


def test_work_cap_fails_before_score_accumulation() -> None:
    hypotheses = _basic_hypotheses()
    evidence = _evidence(
        hypotheses,
        ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
    )

    with pytest.raises(LongArcHypothesisClosureWorkLimitError, match="score-cell"):
        close_long_arc_hypotheses(
            evidence,
            LongArcHypothesisClosureConfig(maximum_score_cells=5),
        )


def test_log_prior_authority_retains_a_state_whose_linear_mass_underflows() -> None:
    hypotheses = (
        _prior(
            "null-half",
            family="h0-radio-null",
            probability=0.5,
            connected_neighborhood="radio-null",
        ),
        _prior(
            "ordinary-half",
            family="h1-single-candidate",
            probability=0.5,
            connected_neighborhood="ordinary",
            catalog_numbers=(65438,),
            tau_s=(0.0,),
        ),
        LongArcHypothesisPrior(
            hypothesis_id=_digest("hypothesis:tiny-log-prior"),
            family="h1-single-candidate",
            normalized_log_prior_probability=-1_000.0,
            connected_neighborhood_label="tiny-but-retained",
            catalog_numbers=(59748,),
            tau_s=(0.0,),
            nuisance_model_reference_digest=_digest("nuisance-model:tiny"),
        ),
    )
    assert hypotheses[-1].prior_probability == 0.0
    assert hypotheses[-1].prior_probability_representable is False

    result = close_long_arc_hypotheses(_evidence(hypotheses, ((-100.0, -100.0, 1_000.0),)))

    retained = next(
        item
        for item in result.final_hypothesis_posterior
        if item.connected_neighborhood_label == "tiny-but-retained"
    )
    assert retained.normalized_log_prior_probability == -1_000.0
    assert retained.prior_probability == 0.0
    assert retained.prior_probability_representable is False
    assert retained.posterior_probability > 0.99
    assert result.final_summary.outcome is not None
    assert result.final_summary.outcome.outcome == "singleton"


def test_family_shapes_fail_closed() -> None:
    with pytest.raises(LongArcHypothesisClosureInputError, match="exactly one"):
        _prior(
            "bad-h1",
            family="h1-single-candidate",
            probability=0.5,
            connected_neighborhood="bad",
            catalog_numbers=(1, 2),
            tau_s=(0.0, 0.0),
        )
    with pytest.raises(LongArcHypothesisClosureInputError, match="two distinct"):
        _prior(
            "bad-k2",
            family="k2-two-candidate",
            probability=0.5,
            connected_neighborhood="bad",
            catalog_numbers=(1, 1),
            tau_s=(0.0, 0.0),
        )
