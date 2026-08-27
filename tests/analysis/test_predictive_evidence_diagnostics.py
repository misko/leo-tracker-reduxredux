from __future__ import annotations

import math
from dataclasses import replace

import pytest

from leo.analysis.nearest_neighbour_association import (
    NearestNeighbourAssociationResult,
    NearestNeighbourHypothesisScore,
    NearestNeighbourTauProfilePoint,
    gaussian_innovation_score,
)
from leo.analysis.research.predictive_evidence_diagnostics import (
    PredictiveEvidenceInputError,
    audit_catalogue_radio_predictive_evidence,
)
from leo.analysis.research.radio_polynomial_null import (
    RadioPolynomialNullResult,
    RadioPolynomialNullScore,
)
from leo.contracts.digests import canonical_digest


def _radio_score(*, degree: int, residual_rms_hz: float = 2.0) -> RadioPolynomialNullScore:
    observation_count = 4
    variance_hz2 = 4.0
    mahalanobis = observation_count * residual_rms_hz**2 / variance_hz2
    log_determinant = observation_count * math.log(variance_hz2)
    nll = 0.5 * (mahalanobis + log_determinant + observation_count * math.log(2.0 * math.pi))
    dimension = degree + 1
    covariance = tuple(
        tuple(1.0 if row == column else 0.0 for column in range(dimension))
        for row in range(dimension)
    )
    return RadioPolynomialNullScore(
        degree=degree,
        reference_utc_ns=1_800_000_000_000_000_000,
        coefficient_units=tuple(
            "Hz" if index == 0 else f"Hz/s^{index}" for index in range(dimension)
        ),
        coefficients=tuple(0.0 for _ in range(dimension)),
        coefficient_covariance=covariance,
        training_observation_count=6,
        evaluation_observation_count=observation_count,
        evaluation_calendar_block_count=2,
        training_rms_hz=1.0,
        evaluation_pooled_rms_hz=residual_rms_hz,
        evaluation_equal_calendar_block_rms_hz=residual_rms_hz,
        evaluation_predictive_negative_log_likelihood=nll,
        evaluation_predictive_log_determinant_hz2=log_determinant,
        evaluation_predictive_mahalanobis_squared=mahalanobis,
        fit_rank=dimension,
        fit_condition_number=2.0,
    )


def _association_and_radio() -> tuple[
    NearestNeighbourAssociationResult,
    RadioPolynomialNullResult,
]:
    graph_digest = canonical_digest({"graph": "common"})
    training_ids = tuple(canonical_digest({"training": index}) for index in range(6))
    evaluation_ids = tuple(canonical_digest({"evaluation": index}) for index in range(4))
    training_innovation = gaussian_innovation_score(
        (0.5, -0.5, 0.5, -0.5, 0.5, -0.5),
        (2.0,) * 6,
        (0.0,) * 6,
        offset_prior_standard_uncertainty_hz=100.0,
    )
    heldout_innovation = gaussian_innovation_score(
        (1.0, -1.0, 1.0, -1.0),
        (100.0,) * 4,
        (0.0,) * 4,
        offset_prior_mean_hz=training_innovation.offset_posterior_mean_hz,
        offset_prior_standard_uncertainty_hz=(
            training_innovation.offset_posterior_standard_uncertainty_hz
        ),
    )
    tau_point = NearestNeighbourTauProfilePoint(
        tau_s=0.0,
        tau_negative_log_prior=0.0,
        training_marginal_negative_log_likelihood=(
            training_innovation.marginal_negative_log_likelihood
        ),
        training_total_negative_log_score=training_innovation.marginal_negative_log_likelihood,
        offset_posterior_mean_hz=training_innovation.offset_posterior_mean_hz,
        offset_posterior_standard_uncertainty_hz=(
            training_innovation.offset_posterior_standard_uncertainty_hz
        ),
    )
    candidate = NearestNeighbourHypothesisScore(
        training_rank=1,
        heldout_rank=1,
        kind="catalogue-candidate",
        catalog_number=67930,
        selected_tau_s=0.0,
        tau_boundary_hit=False,
        tau_profile_exact_tie=False,
        tau_profile_exact_tie_tolerance=None,
        tau_profile_tied_values_s=(0.0,),
        tau_profile_boundary_tie=False,
        profiled_tau_state_count=1,
        tau_profile_training_scores=(tau_point,),
        tau_negative_log_prior=0.0,
        training_total_negative_log_score=training_innovation.marginal_negative_log_likelihood,
        training_innovation=training_innovation,
        frozen_training_offset_mean_hz=training_innovation.offset_posterior_mean_hz,
        frozen_training_offset_standard_uncertainty_hz=(
            training_innovation.offset_posterior_standard_uncertainty_hz
        ),
        heldout_predictive_negative_log_score=(heldout_innovation.marginal_negative_log_likelihood),
        heldout_innovation=heldout_innovation,
    )
    association = NearestNeighbourAssociationResult(
        graph_content_digest=graph_digest,
        prediction_bank_content_digest=canonical_digest({"bank": "common"}),
        candidate_universe_digest=canonical_digest({"universe": "common"}),
        observation_partition_digest=canonical_digest({"partition": "catalogue"}),
        training_observation_ids=training_ids,
        evaluation_observation_ids=evaluation_ids,
        selection_protocol_digest=canonical_digest({"protocol": "common"}),
        selection_policy_digest=canonical_digest({"policy": "common"}),
        nuisance_offset_prior_sigma_hz=100.0,
        restricted_null_prediction_cfo_hz=0.0,
        restricted_null_prediction_standard_uncertainty_hz=50.0,
        descriptive_ambiguity_negative_log_score_margin=None,
        descriptive_mean_normalized_innovation_squared_threshold=None,
        evaluated_catalogue_candidate_count=488,
        ineligible_catalogue_candidate_count=0,
        profiled_tau_state_count=1,
        scores=(candidate,),
        training_nearest_kind="catalogue-candidate",
        training_nearest_catalog_number=67930,
        training_runner_kind=None,
        training_runner_catalog_number=None,
        training_runner_negative_log_score_margin=None,
        training_exact_tie_tolerance=None,
        training_exact_tie=False,
        training_ambiguous_under_descriptive_margin=None,
        training_innovation_threshold_exceeded=None,
        training_nearest_heldout_rank=1,
        training_nearest_persisted_on_heldout=True,
        heldout_nearest_kind="catalogue-candidate",
        heldout_nearest_catalog_number=67930,
        heldout_runner_kind=None,
        heldout_runner_catalog_number=None,
        heldout_runner_negative_log_score_margin=None,
        heldout_exact_tie_tolerance=None,
        heldout_exact_tie=False,
        heldout_innovation_threshold_exceeded=None,
        tau_boundary_diagnostic=False,
        training_nearest_tau_profile_exact_tie=False,
        training_nearest_tau_profile_boundary_tie=False,
        restricted_null_selected_on_training=False,
        abstention_recommended=False,
        abstention_diagnostics=(),
        descriptive_diagnostics=(),
    )
    radio = RadioPolynomialNullResult(
        graph_content_digest=graph_digest,
        observation_partition_digest=canonical_digest({"partition": "radio"}),
        training_observation_ids=training_ids,
        evaluation_observation_ids=evaluation_ids,
        scores=tuple(_radio_score(degree=degree) for degree in (1, 2, 3)),
    )
    return association, radio


def test_decomposes_rms_nll_disagreement_without_creating_a_gate() -> None:
    association, radio = _association_and_radio()

    audit = audit_catalogue_radio_predictive_evidence(
        association,
        radio,
        catalogue_training_rank=1,
    )

    assert audit.catalogue_number == 67930
    assert audit.catalogue_candidate_search_count == 488
    assert len(audit.comparisons) == 3
    comparison = audit.comparisons[2]
    assert comparison.catalogue.future_residual_rms_hz == pytest.approx(1.0)
    assert comparison.radio.future_residual_rms_hz == pytest.approx(2.0)
    assert comparison.rms_preference == "catalogue-orbit"
    assert comparison.predictive_nll_preference == "radio-polynomial"
    assert comparison.preference_disagrees is True
    assert comparison.radio_minus_catalogue_total_predictive_nll == pytest.approx(
        comparison.radio_minus_catalogue_residual_fit_nll_component
        + comparison.radio_minus_catalogue_uncertainty_volume_nll_component,
    )
    assert "rms-and-nll-preference-disagree" in audit.diagnostics
    assert audit.cross_model_uncertainty_calibrated is False
    assert audit.search_multiplicity_normalized_across_families is False
    assert audit.posterior_probability_produced is False
    assert audit.model_selection_gate_produced is False
    assert audit.identity_claimed is False


def test_same_common_partition_is_required() -> None:
    association, radio = _association_and_radio()
    changed = replace(
        radio,
        evaluation_observation_ids=tuple(reversed(radio.evaluation_observation_ids)),
    )

    with pytest.raises(PredictiveEvidenceInputError, match="future inventories differ"):
        audit_catalogue_radio_predictive_evidence(
            association,
            changed,
            catalogue_training_rank=1,
        )


def test_gaussian_score_decomposition_is_revalidated() -> None:
    association, radio = _association_and_radio()
    score = radio.scores[0]
    poisoned_score = replace(
        score,
        evaluation_predictive_negative_log_likelihood=(
            score.evaluation_predictive_negative_log_likelihood + 1.0
        ),
    )
    poisoned = replace(radio, scores=(poisoned_score, *radio.scores[1:]))

    with pytest.raises(PredictiveEvidenceInputError, match="does not match"):
        audit_catalogue_radio_predictive_evidence(
            association,
            poisoned,
            catalogue_training_rank=1,
        )


def test_catalogue_rank_must_select_one_catalogue_hypothesis() -> None:
    association, radio = _association_and_radio()

    with pytest.raises(PredictiveEvidenceInputError, match="missing or duplicated"):
        audit_catalogue_radio_predictive_evidence(
            association,
            radio,
            catalogue_training_rank=2,
        )


def test_future_row_count_must_match() -> None:
    association, radio = _association_and_radio()
    changed_score = replace(radio.scores[0], evaluation_observation_count=3)
    changed = replace(radio, scores=(changed_score, *radio.scores[1:]))

    with pytest.raises(PredictiveEvidenceInputError, match="future row counts differ"):
        audit_catalogue_radio_predictive_evidence(
            association,
            changed,
            catalogue_training_rank=1,
        )
