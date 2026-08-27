"""Comparable future-score diagnostics for catalogue and radio-only models.

The catalogue nearest-neighbour lane and the radio-polynomial lane both score
one frozen future partition with a proper Gaussian predictive density.  Their
raw residual RMS and predictive negative log likelihood (NLL) can nevertheless
prefer different models because NLL contains both a residual-fit term and an
uncertainty-volume term.  This pure analyzer makes that decomposition explicit
on the exact common observation inventory.

The output is deliberately not a Bayes factor, posterior probability, model
selection gate, or uncertainty calibration result.  Candidate/tau/model-degree
selection uncertainty and catalogue multiplicity are not marginalized across
the two families, and the real-data uncertainty models have not yet been
calibrated on known truth.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

from leo.analysis.nearest_neighbour_association import (
    NearestNeighbourAssociationResult,
    NearestNeighbourHypothesisScore,
)
from leo.analysis.research.radio_polynomial_null import (
    RadioPolynomialNullResult,
    RadioPolynomialNullScore,
)

type PredictiveModelKind = Literal["catalogue-orbit", "radio-polynomial"]
type ScorePreference = Literal["catalogue-orbit", "radio-polynomial", "exact-tie"]
type NisDirection = Literal["below-one", "equal-one-within-float", "above-one"]
type EvidenceDiagnostic = Literal[
    "cross-model-uncertainty-not-calibrated",
    "rms-and-nll-preference-disagree",
    "search-multiplicity-not-normalized",
]


class PredictiveEvidenceInputError(ValueError):
    """The two result families do not describe one comparable future score."""


class PredictiveEvidenceNumericalError(ValueError):
    """A predictive-score decomposition is not numerically representable."""


@dataclass(frozen=True, slots=True)
class PredictiveEvidenceModelSummary:
    """One frozen model's future score and exact Gaussian decomposition."""

    model_kind: PredictiveModelKind
    model_label: str
    observation_count: int
    future_residual_rms_hz: float
    mahalanobis_squared: float
    mean_normalized_innovation_squared: float
    nis_direction: NisDirection
    log_determinant_covariance: float
    geometric_mean_predictive_standard_uncertainty_hz: float
    residual_fit_negative_log_likelihood_component: float
    uncertainty_volume_negative_log_likelihood_component: float
    gaussian_normalization_negative_log_likelihood_component: float
    total_predictive_negative_log_likelihood: float
    predictive_negative_log_likelihood_per_observation: float
    fitted_continuous_parameter_count: int
    profiled_discrete_state_count: int
    training_search_family_size: int


@dataclass(frozen=True, slots=True)
class CatalogueRadioPredictiveEvidenceComparison:
    """One catalogue candidate versus one frozen polynomial degree."""

    polynomial_degree: int
    catalogue: PredictiveEvidenceModelSummary
    radio: PredictiveEvidenceModelSummary
    radio_minus_catalogue_residual_rms_hz: float
    radio_minus_catalogue_mahalanobis_squared: float
    radio_minus_catalogue_log_determinant_covariance: float
    radio_minus_catalogue_residual_fit_nll_component: float
    radio_minus_catalogue_uncertainty_volume_nll_component: float
    radio_minus_catalogue_total_predictive_nll: float
    rms_preference: ScorePreference
    predictive_nll_preference: ScorePreference
    preference_disagrees: bool


@dataclass(frozen=True, slots=True)
class CatalogueRadioPredictiveEvidenceAudit:
    """Common-partition score audit with intentionally limited interpretation."""

    graph_content_digest: str
    training_observation_ids: tuple[str, ...]
    evaluation_observation_ids: tuple[str, ...]
    catalogue_number: int
    catalogue_training_rank: int
    selected_tau_s: float
    catalogue_candidate_search_count: int
    catalogue_tau_state_count: int
    comparisons: tuple[CatalogueRadioPredictiveEvidenceComparison, ...]
    diagnostics: tuple[EvidenceDiagnostic, ...]
    algorithm_version: Literal["common-future-predictive-evidence-decomposition-v1"] = field(
        default="common-future-predictive-evidence-decomposition-v1", init=False
    )
    exact_common_future_partition: Literal[True] = field(default=True, init=False)
    future_scores_frozen_without_refit: Literal[True] = field(default=True, init=False)
    thresholds_are_unset: Literal[True] = field(default=True, init=False)
    cross_model_uncertainty_calibrated: Literal[False] = field(default=False, init=False)
    search_multiplicity_normalized_across_families: Literal[False] = field(
        default=False, init=False
    )
    posterior_probability_produced: Literal[False] = field(default=False, init=False)
    model_selection_gate_produced: Literal[False] = field(default=False, init=False)
    identity_claimed: Literal[False] = field(default=False, init=False)


def audit_catalogue_radio_predictive_evidence(
    association: NearestNeighbourAssociationResult,
    radio_null: RadioPolynomialNullResult,
    *,
    catalogue_training_rank: int,
) -> CatalogueRadioPredictiveEvidenceAudit:
    """Decompose catalogue-versus-radio scores on one exact future partition.

    ``catalogue_training_rank`` is explicit because the caller may inspect the
    best catalogue candidate even when the restricted radio/null hypothesis was
    ranked ahead of it during training.  The selected catalogue hypothesis must
    itself have been frozen on training and scored once on the future suffix.
    """

    _validate_common_partition(association, radio_null)
    catalogue_score = _catalogue_score(association, catalogue_training_rank)
    catalogue_summary = _summarize_catalogue_score(
        catalogue_score,
        catalogue_candidate_search_count=association.evaluated_catalogue_candidate_count,
    )
    comparisons = tuple(
        _compare(
            catalogue_summary,
            _summarize_radio_score(score),
            polynomial_degree=score.degree,
        )
        for score in radio_null.scores
    )
    diagnostics: list[EvidenceDiagnostic] = [
        "cross-model-uncertainty-not-calibrated",
        "search-multiplicity-not-normalized",
    ]
    if any(item.preference_disagrees for item in comparisons):
        diagnostics.append("rms-and-nll-preference-disagree")
    diagnostics.sort()
    if catalogue_score.catalog_number is None or catalogue_score.selected_tau_s is None:
        raise PredictiveEvidenceInputError("catalogue score lacks a NORAD or selected tau")
    return CatalogueRadioPredictiveEvidenceAudit(
        graph_content_digest=association.graph_content_digest,
        training_observation_ids=association.training_observation_ids,
        evaluation_observation_ids=association.evaluation_observation_ids,
        catalogue_number=catalogue_score.catalog_number,
        catalogue_training_rank=catalogue_score.training_rank,
        selected_tau_s=catalogue_score.selected_tau_s,
        catalogue_candidate_search_count=association.evaluated_catalogue_candidate_count,
        catalogue_tau_state_count=catalogue_score.profiled_tau_state_count,
        comparisons=comparisons,
        diagnostics=tuple(diagnostics),
    )


def _validate_common_partition(
    association: NearestNeighbourAssociationResult,
    radio_null: RadioPolynomialNullResult,
) -> None:
    if association.graph_content_digest != radio_null.graph_content_digest:
        raise PredictiveEvidenceInputError("catalogue and radio scores use different graphs")
    if association.training_observation_ids != radio_null.training_observation_ids:
        raise PredictiveEvidenceInputError("catalogue and radio training inventories differ")
    if association.evaluation_observation_ids != radio_null.evaluation_observation_ids:
        raise PredictiveEvidenceInputError("catalogue and radio future inventories differ")
    training = association.training_observation_ids
    evaluation = association.evaluation_observation_ids
    if not training or not evaluation:
        raise PredictiveEvidenceInputError(
            "predictive comparison requires training and future rows"
        )
    if (
        len(set(training)) != len(training)
        or len(set(evaluation)) != len(evaluation)
        or set(training) & set(evaluation)
    ):
        raise PredictiveEvidenceInputError("predictive partition must be unique and disjoint")
    if not association.heldout_rows_scored_once_without_refit:
        raise PredictiveEvidenceInputError("catalogue future rows were not frozen before scoring")
    if not radio_null.future_scored_once_without_refit:
        raise PredictiveEvidenceInputError("radio future rows were not frozen before scoring")
    if association.likelihoods_are_calibrated_identity_probabilities:
        raise PredictiveEvidenceInputError("catalogue score has an unsupported probability claim")
    if radio_null.identity_probability_produced or radio_null.association_gate_produced:
        raise PredictiveEvidenceInputError("radio null has an unsupported identity claim")
    degrees = tuple(item.degree for item in radio_null.scores)
    if degrees != (1, 2, 3):
        raise PredictiveEvidenceInputError("radio degree inventory must be line/quadratic/cubic")
    if any(item.evaluation_observation_count != len(evaluation) for item in radio_null.scores):
        raise PredictiveEvidenceInputError("catalogue and radio future row counts differ")


def _catalogue_score(
    association: NearestNeighbourAssociationResult,
    training_rank: int,
) -> NearestNeighbourHypothesisScore:
    if training_rank < 1:
        raise PredictiveEvidenceInputError("catalogue training rank must be positive")
    matches = tuple(item for item in association.scores if item.training_rank == training_rank)
    if len(matches) != 1:
        raise PredictiveEvidenceInputError("catalogue training rank is missing or duplicated")
    score = matches[0]
    if score.kind != "catalogue-candidate":
        raise PredictiveEvidenceInputError("selected training rank is not a catalogue candidate")
    if score.heldout_rank < 1:
        raise PredictiveEvidenceInputError("catalogue heldout rank must be positive")
    if score.heldout_innovation.observation_count != len(association.evaluation_observation_ids):
        raise PredictiveEvidenceInputError("catalogue future score has the wrong row count")
    if not math.isclose(
        score.heldout_predictive_negative_log_score,
        score.heldout_innovation.marginal_negative_log_likelihood,
        rel_tol=1e-12,
        abs_tol=1e-9,
    ):
        raise PredictiveEvidenceInputError("catalogue future score is internally inconsistent")
    return score


def _summarize_catalogue_score(
    score: NearestNeighbourHypothesisScore,
    *,
    catalogue_candidate_search_count: int,
) -> PredictiveEvidenceModelSummary:
    if score.catalog_number is None:
        raise PredictiveEvidenceInputError("catalogue score lacks a NORAD")
    if catalogue_candidate_search_count < 1 or score.profiled_tau_state_count < 1:
        raise PredictiveEvidenceInputError("catalogue search opportunity is invalid")
    innovation = score.heldout_innovation
    return _summary(
        model_kind="catalogue-orbit",
        model_label=f"NORAD-{score.catalog_number}",
        observation_count=innovation.observation_count,
        residual_rms_hz=innovation.prior_centered_innovation_rms_hz,
        mahalanobis_squared=innovation.mahalanobis_squared,
        log_determinant_covariance=innovation.log_determinant_covariance,
        total_nll=innovation.marginal_negative_log_likelihood,
        fitted_continuous_parameter_count=1,
        profiled_discrete_state_count=score.profiled_tau_state_count,
        training_search_family_size=catalogue_candidate_search_count,
    )


def _summarize_radio_score(score: RadioPolynomialNullScore) -> PredictiveEvidenceModelSummary:
    if score.degree not in (1, 2, 3):
        raise PredictiveEvidenceInputError("radio-polynomial degree is unsupported")
    return _summary(
        model_kind="radio-polynomial",
        model_label=f"degree-{score.degree}",
        observation_count=score.evaluation_observation_count,
        residual_rms_hz=score.evaluation_pooled_rms_hz,
        mahalanobis_squared=score.evaluation_predictive_mahalanobis_squared,
        log_determinant_covariance=score.evaluation_predictive_log_determinant_hz2,
        total_nll=score.evaluation_predictive_negative_log_likelihood,
        fitted_continuous_parameter_count=score.degree + 1,
        profiled_discrete_state_count=1,
        training_search_family_size=1,
    )


def _summary(
    *,
    model_kind: PredictiveModelKind,
    model_label: str,
    observation_count: int,
    residual_rms_hz: float,
    mahalanobis_squared: float,
    log_determinant_covariance: float,
    total_nll: float,
    fitted_continuous_parameter_count: int,
    profiled_discrete_state_count: int,
    training_search_family_size: int,
) -> PredictiveEvidenceModelSummary:
    values = (residual_rms_hz, mahalanobis_squared, log_determinant_covariance, total_nll)
    if observation_count < 1 or fitted_continuous_parameter_count < 1:
        raise PredictiveEvidenceInputError("predictive model counts must be positive")
    if profiled_discrete_state_count < 1 or training_search_family_size < 1:
        raise PredictiveEvidenceInputError("predictive search counts must be positive")
    if any(not math.isfinite(item) for item in values):
        raise PredictiveEvidenceInputError("predictive score terms must be finite")
    if residual_rms_hz < 0.0 or mahalanobis_squared < 0.0:
        raise PredictiveEvidenceInputError("predictive residual and quadratic must be nonnegative")
    residual_component = 0.5 * mahalanobis_squared
    uncertainty_component = 0.5 * log_determinant_covariance
    normalization_component = 0.5 * observation_count * math.log(2.0 * math.pi)
    reconstructed = residual_component + uncertainty_component + normalization_component
    tolerance = max(1e-9, 32.0 * math.ulp(max(1.0, abs(reconstructed), abs(total_nll))))
    if abs(reconstructed - total_nll) > tolerance:
        raise PredictiveEvidenceInputError("predictive NLL does not match its Gaussian terms")
    try:
        geometric_sigma = math.exp(log_determinant_covariance / (2.0 * observation_count))
    except OverflowError as error:
        raise PredictiveEvidenceNumericalError(
            "geometric predictive uncertainty is not representable"
        ) from error
    if not math.isfinite(geometric_sigma) or geometric_sigma <= 0.0:
        raise PredictiveEvidenceNumericalError(
            "geometric predictive uncertainty is not finite and positive"
        )
    mean_nis = mahalanobis_squared / observation_count
    return PredictiveEvidenceModelSummary(
        model_kind=model_kind,
        model_label=model_label,
        observation_count=observation_count,
        future_residual_rms_hz=residual_rms_hz,
        mahalanobis_squared=mahalanobis_squared,
        mean_normalized_innovation_squared=mean_nis,
        nis_direction=_nis_direction(mean_nis),
        log_determinant_covariance=log_determinant_covariance,
        geometric_mean_predictive_standard_uncertainty_hz=geometric_sigma,
        residual_fit_negative_log_likelihood_component=residual_component,
        uncertainty_volume_negative_log_likelihood_component=uncertainty_component,
        gaussian_normalization_negative_log_likelihood_component=normalization_component,
        total_predictive_negative_log_likelihood=total_nll,
        predictive_negative_log_likelihood_per_observation=total_nll / observation_count,
        fitted_continuous_parameter_count=fitted_continuous_parameter_count,
        profiled_discrete_state_count=profiled_discrete_state_count,
        training_search_family_size=training_search_family_size,
    )


def _compare(
    catalogue: PredictiveEvidenceModelSummary,
    radio: PredictiveEvidenceModelSummary,
    *,
    polynomial_degree: int,
) -> CatalogueRadioPredictiveEvidenceComparison:
    if catalogue.observation_count != radio.observation_count:
        raise PredictiveEvidenceInputError("catalogue and radio future row counts differ")
    rms_preference = _lower_is_better(
        catalogue.future_residual_rms_hz,
        radio.future_residual_rms_hz,
    )
    nll_preference = _lower_is_better(
        catalogue.total_predictive_negative_log_likelihood,
        radio.total_predictive_negative_log_likelihood,
    )
    return CatalogueRadioPredictiveEvidenceComparison(
        polynomial_degree=polynomial_degree,
        catalogue=catalogue,
        radio=radio,
        radio_minus_catalogue_residual_rms_hz=(
            radio.future_residual_rms_hz - catalogue.future_residual_rms_hz
        ),
        radio_minus_catalogue_mahalanobis_squared=(
            radio.mahalanobis_squared - catalogue.mahalanobis_squared
        ),
        radio_minus_catalogue_log_determinant_covariance=(
            radio.log_determinant_covariance - catalogue.log_determinant_covariance
        ),
        radio_minus_catalogue_residual_fit_nll_component=(
            radio.residual_fit_negative_log_likelihood_component
            - catalogue.residual_fit_negative_log_likelihood_component
        ),
        radio_minus_catalogue_uncertainty_volume_nll_component=(
            radio.uncertainty_volume_negative_log_likelihood_component
            - catalogue.uncertainty_volume_negative_log_likelihood_component
        ),
        radio_minus_catalogue_total_predictive_nll=(
            radio.total_predictive_negative_log_likelihood
            - catalogue.total_predictive_negative_log_likelihood
        ),
        rms_preference=rms_preference,
        predictive_nll_preference=nll_preference,
        preference_disagrees=rms_preference != nll_preference,
    )


def _lower_is_better(catalogue: float, radio: float) -> ScorePreference:
    tolerance = 8.0 * math.ulp(max(1.0, abs(catalogue), abs(radio)))
    if abs(catalogue - radio) <= tolerance:
        return "exact-tie"
    return "catalogue-orbit" if catalogue < radio else "radio-polynomial"


def _nis_direction(value: float) -> NisDirection:
    tolerance = 8.0 * math.ulp(max(1.0, abs(value)))
    if abs(value - 1.0) <= tolerance:
        return "equal-one-within-float"
    return "below-one" if value < 1.0 else "above-one"


__all__ = [
    "CatalogueRadioPredictiveEvidenceAudit",
    "CatalogueRadioPredictiveEvidenceComparison",
    "PredictiveEvidenceInputError",
    "PredictiveEvidenceModelSummary",
    "PredictiveEvidenceNumericalError",
    "audit_catalogue_radio_predictive_evidence",
]
