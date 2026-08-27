"""Known-truth audit of catalogue-orbit versus radio-polynomial prediction.

The two model families are first calibrated independently with evidence-disjoint
uniform covariance scales.  This module then compares their scaled predictive
scores on paired, identical-row known-truth cases.  Cases are aggregated within
response-free scenario groups before accuracy is summarized, so duplicated rows
or fragments cannot manufacture evidence.

The result is deliberately descriptive.  It does not fit a decision threshold,
produce posterior odds, or authorize satellite identity.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

from leo.analysis.research.predictive_evidence_diagnostics import (
    CatalogueRadioPredictiveEvidenceAudit,
    PredictiveEvidenceModelSummary,
)
from leo.analysis.research.predictive_uncertainty_calibration import (
    AppliedPredictiveCovarianceScale,
    PredictiveCalibrationInputError,
    PredictiveCovarianceScaleCalibration,
    apply_uniform_predictive_covariance_scale,
)

type TruthModelFamily = Literal["catalogue-orbit", "radio-polynomial"]
type CalibratedPreference = Literal["catalogue-orbit", "radio-polynomial", "exact-tie"]

_INDEPENDENCE_ATTESTATION = "scenario-groups-frozen-response-free-and-independent-v1"
_SHA256_PREFIX = "sha256:"
_SHA256_HEX_LENGTH = 64
_TRUTH_FAMILIES: tuple[TruthModelFamily, TruthModelFamily] = (
    "catalogue-orbit",
    "radio-polynomial",
)


class CrossFamilyCalibrationInputError(ValueError):
    """The paired known-truth calibration inventory is not trustworthy."""


class CrossFamilyCalibrationNumericalError(ValueError):
    """A paired score or scenario aggregation is not representable."""


@dataclass(frozen=True, slots=True)
class CrossFamilyKnownTruthCase:
    case_id: str
    scenario_id: str
    evidence_digest: str
    truth_digest: str
    truth_model_family: TruthModelFamily
    catalogue_model_configuration_digest: str
    radio_model_configuration_digest: str
    audit: CatalogueRadioPredictiveEvidenceAudit


@dataclass(frozen=True, slots=True)
class CrossFamilyCalibrationConfig:
    expected_case_ids: tuple[str, ...]
    polynomial_degree: Literal[1, 2, 3]
    catalogue_model_configuration_digest: str
    radio_model_configuration_digest: str
    independence_attestation: Literal["scenario-groups-frozen-response-free-and-independent-v1"]
    minimum_paired_scenarios: int = 3
    formal_95_percent_rank_minimum_paired_scenarios: int = 19

    def __post_init__(self) -> None:
        if not self.expected_case_ids or len(set(self.expected_case_ids)) != len(
            self.expected_case_ids
        ):
            raise CrossFamilyCalibrationInputError("paired case inventory must be unique")
        if any(not item.strip() for item in self.expected_case_ids):
            raise CrossFamilyCalibrationInputError("paired case identities cannot be empty")
        if self.polynomial_degree not in (1, 2, 3):
            raise CrossFamilyCalibrationInputError("polynomial degree must be line/quadratic/cubic")
        if not _is_digest(self.catalogue_model_configuration_digest) or not _is_digest(
            self.radio_model_configuration_digest
        ):
            raise CrossFamilyCalibrationInputError("paired model configurations need digests")
        if self.independence_attestation != _INDEPENDENCE_ATTESTATION:
            raise CrossFamilyCalibrationInputError(
                "paired scenarios need the frozen independence attestation"
            )
        if self.minimum_paired_scenarios < 3:
            raise CrossFamilyCalibrationInputError(
                "paired calibration needs at least three independent paired scenarios"
            )
        if self.formal_95_percent_rank_minimum_paired_scenarios < 19:
            raise CrossFamilyCalibrationInputError(
                "finite 95 percent rank summaries need at least 19 paired scenarios"
            )


@dataclass(frozen=True, slots=True)
class CrossFamilyKnownTruthCaseScore:
    case_id: str
    scenario_id: str
    truth_model_family: TruthModelFamily
    catalogue: AppliedPredictiveCovarianceScale
    radio: AppliedPredictiveCovarianceScale
    radio_minus_catalogue_scaled_predictive_nll: float
    calibrated_preference: CalibratedPreference
    preference_matches_truth: bool


@dataclass(frozen=True, slots=True)
class CrossFamilyScenarioDiagnostic:
    scenario_id: str
    truth_model_family: TruthModelFamily
    case_count: int
    scenario_mean_radio_minus_catalogue_scaled_predictive_nll: float
    calibrated_preference: CalibratedPreference
    preference_matches_truth: bool


@dataclass(frozen=True, slots=True)
class CrossFamilyPredictiveCalibrationAudit:
    polynomial_degree: int
    catalogue_model_configuration_digest: str
    radio_model_configuration_digest: str
    case_ids: tuple[str, ...]
    evidence_digests: tuple[str, ...]
    truth_digests: tuple[str, ...]
    case_scores: tuple[CrossFamilyKnownTruthCaseScore, ...]
    scenario_diagnostics: tuple[CrossFamilyScenarioDiagnostic, ...]
    catalogue_truth_scenario_count: int
    radio_truth_scenario_count: int
    independent_paired_scenario_count: int
    correct_scenario_count: int
    tied_scenario_count: int
    scenario_equal_accuracy: float
    formal_95_percent_rank_minimum_paired_scenarios: int
    formal_95_percent_rank_scenario_count_sufficient: bool
    algorithm_version: Literal["known-truth-cross-family-predictive-audit-v1"] = field(
        default="known-truth-cross-family-predictive-audit-v1", init=False
    )
    independently_scaled_model_covariances: Literal[True] = field(default=True, init=False)
    scenario_equal_primary: Literal[True] = field(default=True, init=False)
    threshold_fitted: Literal[False] = field(default=False, init=False)
    formal_coverage_claimed: Literal[False] = field(default=False, init=False)
    posterior_odds_produced: Literal[False] = field(default=False, init=False)
    model_selection_gate_produced: Literal[False] = field(default=False, init=False)
    identity_claimed: Literal[False] = field(default=False, init=False)


def audit_known_truth_cross_family_prediction(
    cases: tuple[CrossFamilyKnownTruthCase, ...],
    config: CrossFamilyCalibrationConfig,
    *,
    catalogue_covariance_calibration: PredictiveCovarianceScaleCalibration,
    radio_covariance_calibration: PredictiveCovarianceScaleCalibration,
) -> CrossFamilyPredictiveCalibrationAudit:
    """Compare independently scaled model families on paired known truth."""

    config = _revalidate_config(config)
    cases = tuple(
        _revalidate_case(item, polynomial_degree=config.polynomial_degree) for item in cases
    )
    if tuple(item.case_id for item in cases) != config.expected_case_ids:
        raise CrossFamilyCalibrationInputError(
            "paired case inventory differs from the frozen configuration"
        )
    if len({item.evidence_digest for item in cases}) != len(cases):
        raise CrossFamilyCalibrationInputError("paired evidence must not be duplicated")
    if any(
        item.catalogue_model_configuration_digest != config.catalogue_model_configuration_digest
        or item.radio_model_configuration_digest != config.radio_model_configuration_digest
        for item in cases
    ):
        raise CrossFamilyCalibrationInputError(
            "paired case model configuration differs from the frozen configuration"
        )
    by_scenario: dict[str, list[CrossFamilyKnownTruthCase]] = {}
    for case in cases:
        by_scenario.setdefault(case.scenario_id, []).append(case)
    scenario_ids = tuple(sorted(by_scenario))
    for scenario_id, scenario_cases in by_scenario.items():
        families = {item.truth_model_family for item in scenario_cases}
        if families != {"catalogue-orbit", "radio-polynomial"}:
            raise CrossFamilyCalibrationInputError(
                f"scenario {scenario_id} must contain both paired truth arms"
            )
        for family in families:
            truth_digests = {
                item.truth_digest for item in scenario_cases if item.truth_model_family == family
            }
            if len(truth_digests) != 1:
                raise CrossFamilyCalibrationInputError(
                    f"scenario {scenario_id} mixes truth authorities within one arm"
                )
    if len(scenario_ids) < config.minimum_paired_scenarios:
        raise CrossFamilyCalibrationInputError("too few independent paired scenarios")

    case_scores = tuple(
        _score_case(
            case,
            polynomial_degree=config.polynomial_degree,
            catalogue_configuration_digest=config.catalogue_model_configuration_digest,
            radio_configuration_digest=config.radio_model_configuration_digest,
            catalogue_calibration=catalogue_covariance_calibration,
            radio_calibration=radio_covariance_calibration,
        )
        for case in cases
    )
    scenario_diagnostics = tuple(
        _scenario_diagnostic(
            scenario_id,
            family,
            tuple(
                item
                for item in case_scores
                if item.scenario_id == scenario_id and item.truth_model_family == family
            ),
        )
        for scenario_id in scenario_ids
        for family in _TRUTH_FAMILIES
    )
    correct = sum(item.preference_matches_truth for item in scenario_diagnostics)
    tied = sum(item.calibrated_preference == "exact-tie" for item in scenario_diagnostics)
    return CrossFamilyPredictiveCalibrationAudit(
        polynomial_degree=config.polynomial_degree,
        catalogue_model_configuration_digest=config.catalogue_model_configuration_digest,
        radio_model_configuration_digest=config.radio_model_configuration_digest,
        case_ids=tuple(item.case_id for item in cases),
        evidence_digests=tuple(item.evidence_digest for item in cases),
        truth_digests=tuple(item.truth_digest for item in cases),
        case_scores=case_scores,
        scenario_diagnostics=scenario_diagnostics,
        catalogue_truth_scenario_count=len(scenario_ids),
        radio_truth_scenario_count=len(scenario_ids),
        independent_paired_scenario_count=len(scenario_ids),
        correct_scenario_count=correct,
        tied_scenario_count=tied,
        scenario_equal_accuracy=correct / len(scenario_diagnostics),
        formal_95_percent_rank_minimum_paired_scenarios=(
            config.formal_95_percent_rank_minimum_paired_scenarios
        ),
        formal_95_percent_rank_scenario_count_sufficient=(
            len(scenario_ids) >= config.formal_95_percent_rank_minimum_paired_scenarios
        ),
    )


def _score_case(
    case: CrossFamilyKnownTruthCase,
    *,
    polynomial_degree: int,
    catalogue_configuration_digest: str,
    radio_configuration_digest: str,
    catalogue_calibration: PredictiveCovarianceScaleCalibration,
    radio_calibration: PredictiveCovarianceScaleCalibration,
) -> CrossFamilyKnownTruthCaseScore:
    comparison = next(
        item for item in case.audit.comparisons if item.polynomial_degree == polynomial_degree
    )
    try:
        catalogue = apply_uniform_predictive_covariance_scale(
            comparison.catalogue,
            catalogue_calibration,
            target_group_id=case.case_id,
            target_evidence_digest=case.evidence_digest,
            model_configuration_digest=catalogue_configuration_digest,
        )
        radio = apply_uniform_predictive_covariance_scale(
            comparison.radio,
            radio_calibration,
            target_group_id=case.case_id,
            target_evidence_digest=case.evidence_digest,
            model_configuration_digest=radio_configuration_digest,
        )
    except PredictiveCalibrationInputError as error:
        raise CrossFamilyCalibrationInputError(
            "paired target is not disjoint from covariance calibration"
        ) from error
    delta = _finite_difference(
        radio.scaled_predictive_negative_log_likelihood,
        catalogue.scaled_predictive_negative_log_likelihood,
        "paired scaled predictive score",
    )
    preference = _preference(delta)
    return CrossFamilyKnownTruthCaseScore(
        case_id=case.case_id,
        scenario_id=case.scenario_id,
        truth_model_family=case.truth_model_family,
        catalogue=catalogue,
        radio=radio,
        radio_minus_catalogue_scaled_predictive_nll=delta,
        calibrated_preference=preference,
        preference_matches_truth=preference == case.truth_model_family,
    )


def _scenario_diagnostic(
    scenario_id: str,
    truth_family: TruthModelFamily,
    cases: tuple[CrossFamilyKnownTruthCaseScore, ...],
) -> CrossFamilyScenarioDiagnostic:
    if not cases:
        raise CrossFamilyCalibrationInputError("scenario has no paired cases")
    try:
        mean_delta = math.fsum(
            item.radio_minus_catalogue_scaled_predictive_nll for item in cases
        ) / len(cases)
    except (OverflowError, ValueError) as error:
        raise CrossFamilyCalibrationNumericalError(
            "scenario mean predictive separation is not representable"
        ) from error
    if not math.isfinite(mean_delta):
        raise CrossFamilyCalibrationNumericalError(
            "scenario mean predictive separation is not finite"
        )
    preference = _preference(mean_delta)
    return CrossFamilyScenarioDiagnostic(
        scenario_id=scenario_id,
        truth_model_family=truth_family,
        case_count=len(cases),
        scenario_mean_radio_minus_catalogue_scaled_predictive_nll=mean_delta,
        calibrated_preference=preference,
        preference_matches_truth=preference == truth_family,
    )


def _revalidate_case(
    value: CrossFamilyKnownTruthCase,
    *,
    polynomial_degree: int,
) -> CrossFamilyKnownTruthCase:
    try:
        copied = CrossFamilyKnownTruthCase(
            case_id=value.case_id,
            scenario_id=value.scenario_id,
            evidence_digest=value.evidence_digest,
            truth_digest=value.truth_digest,
            truth_model_family=value.truth_model_family,
            catalogue_model_configuration_digest=(value.catalogue_model_configuration_digest),
            radio_model_configuration_digest=value.radio_model_configuration_digest,
            audit=value.audit,
        )
    except (AttributeError, TypeError, ValueError) as error:
        raise CrossFamilyCalibrationInputError("paired known-truth case is invalid") from error
    if not copied.case_id.strip() or not copied.scenario_id.strip():
        raise CrossFamilyCalibrationInputError(
            "paired case and scenario identities cannot be empty"
        )
    if not _is_digest(copied.evidence_digest) or not _is_digest(copied.truth_digest):
        raise CrossFamilyCalibrationInputError("paired evidence and truth need digests")
    if copied.truth_model_family not in ("catalogue-orbit", "radio-polynomial"):
        raise CrossFamilyCalibrationInputError("paired truth model family is invalid")
    if not _is_digest(copied.catalogue_model_configuration_digest) or not _is_digest(
        copied.radio_model_configuration_digest
    ):
        raise CrossFamilyCalibrationInputError("paired model configurations need digests")
    _validate_audit(copied.audit, polynomial_degree=polynomial_degree)
    return copied


def _validate_audit(
    audit: CatalogueRadioPredictiveEvidenceAudit,
    *,
    polynomial_degree: int,
) -> None:
    if (
        audit.algorithm_version != "common-future-predictive-evidence-decomposition-v1"
        or not audit.exact_common_future_partition
        or not audit.future_scores_frozen_without_refit
        or not audit.thresholds_are_unset
        or audit.cross_model_uncertainty_calibrated
        or audit.search_multiplicity_normalized_across_families
        or audit.posterior_probability_produced
        or audit.model_selection_gate_produced
        or audit.identity_claimed
    ):
        raise CrossFamilyCalibrationInputError("paired evidence audit violates its claim boundary")
    if not _is_digest(audit.graph_content_digest):
        raise CrossFamilyCalibrationInputError("paired graph must be digest-bound")
    if (
        audit.catalogue_number < 1
        or audit.catalogue_training_rank < 1
        or not math.isfinite(audit.selected_tau_s)
        or audit.catalogue_candidate_search_count < 1
        or audit.catalogue_tau_state_count < 1
        or tuple(item.polynomial_degree for item in audit.comparisons) != (1, 2, 3)
    ):
        raise CrossFamilyCalibrationInputError("paired audit search inventory is invalid")
    if (
        not audit.training_observation_ids
        or not audit.evaluation_observation_ids
        or len(set(audit.training_observation_ids)) != len(audit.training_observation_ids)
        or len(set(audit.evaluation_observation_ids)) != len(audit.evaluation_observation_ids)
        or set(audit.training_observation_ids) & set(audit.evaluation_observation_ids)
    ):
        raise CrossFamilyCalibrationInputError("paired observation inventory is invalid")
    if any(
        not _is_digest(item)
        for item in (*audit.training_observation_ids, *audit.evaluation_observation_ids)
    ):
        raise CrossFamilyCalibrationInputError("paired observation identities need digests")
    matches = tuple(
        item for item in audit.comparisons if item.polynomial_degree == polynomial_degree
    )
    if len(matches) != 1:
        raise CrossFamilyCalibrationInputError("paired audit lacks the frozen polynomial degree")
    comparison = matches[0]
    _validate_summary(comparison.catalogue, expected_kind="catalogue-orbit")
    _validate_summary(comparison.radio, expected_kind="radio-polynomial")
    if comparison.catalogue.observation_count != len(audit.evaluation_observation_ids) or (
        comparison.radio.observation_count != len(audit.evaluation_observation_ids)
    ):
        raise CrossFamilyCalibrationInputError("paired future row count is inconsistent")
    expected_rms_delta = (
        comparison.radio.future_residual_rms_hz - comparison.catalogue.future_residual_rms_hz
    )
    expected_nll_delta = (
        comparison.radio.total_predictive_negative_log_likelihood
        - comparison.catalogue.total_predictive_negative_log_likelihood
    )
    expected_deltas = (
        expected_rms_delta,
        comparison.radio.mahalanobis_squared - comparison.catalogue.mahalanobis_squared,
        comparison.radio.log_determinant_covariance
        - comparison.catalogue.log_determinant_covariance,
        comparison.radio.residual_fit_negative_log_likelihood_component
        - comparison.catalogue.residual_fit_negative_log_likelihood_component,
        comparison.radio.uncertainty_volume_negative_log_likelihood_component
        - comparison.catalogue.uncertainty_volume_negative_log_likelihood_component,
        expected_nll_delta,
    )
    actual_deltas = (
        comparison.radio_minus_catalogue_residual_rms_hz,
        comparison.radio_minus_catalogue_mahalanobis_squared,
        comparison.radio_minus_catalogue_log_determinant_covariance,
        comparison.radio_minus_catalogue_residual_fit_nll_component,
        comparison.radio_minus_catalogue_uncertainty_volume_nll_component,
        comparison.radio_minus_catalogue_total_predictive_nll,
    )
    expected_rms_preference = _lower_is_better(
        comparison.catalogue.future_residual_rms_hz,
        comparison.radio.future_residual_rms_hz,
    )
    expected_nll_preference = _lower_is_better(
        comparison.catalogue.total_predictive_negative_log_likelihood,
        comparison.radio.total_predictive_negative_log_likelihood,
    )
    if any(
        not math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-9)
        for actual, expected in zip(actual_deltas, expected_deltas, strict=True)
    ) or (
        comparison.rms_preference != expected_rms_preference
        or comparison.predictive_nll_preference != expected_nll_preference
        or comparison.preference_disagrees != (expected_rms_preference != expected_nll_preference)
    ):
        raise CrossFamilyCalibrationInputError("paired comparison deltas are inconsistent")


def _validate_summary(
    summary: PredictiveEvidenceModelSummary,
    *,
    expected_kind: TruthModelFamily,
) -> None:
    if summary.model_kind != expected_kind or summary.observation_count < 1:
        raise CrossFamilyCalibrationInputError("paired model summary has the wrong family")
    values = (
        summary.future_residual_rms_hz,
        summary.mahalanobis_squared,
        summary.log_determinant_covariance,
        summary.total_predictive_negative_log_likelihood,
    )
    if any(not math.isfinite(item) for item in values) or min(values[:2]) < 0.0:
        raise CrossFamilyCalibrationInputError("paired model summary is not finite")
    expected_nis = summary.mahalanobis_squared / summary.observation_count
    expected_nll = 0.5 * (
        summary.mahalanobis_squared
        + summary.log_determinant_covariance
        + summary.observation_count * math.log(2.0 * math.pi)
    )
    if not math.isclose(
        summary.mean_normalized_innovation_squared,
        expected_nis,
        rel_tol=1e-12,
        abs_tol=1e-12,
    ) or not math.isclose(
        summary.total_predictive_negative_log_likelihood,
        expected_nll,
        rel_tol=1e-12,
        abs_tol=1e-9,
    ):
        raise CrossFamilyCalibrationInputError("paired model decomposition is inconsistent")


def _revalidate_config(value: CrossFamilyCalibrationConfig) -> CrossFamilyCalibrationConfig:
    try:
        return CrossFamilyCalibrationConfig(
            expected_case_ids=tuple(value.expected_case_ids),
            polynomial_degree=value.polynomial_degree,
            catalogue_model_configuration_digest=value.catalogue_model_configuration_digest,
            radio_model_configuration_digest=value.radio_model_configuration_digest,
            independence_attestation=value.independence_attestation,
            minimum_paired_scenarios=value.minimum_paired_scenarios,
            formal_95_percent_rank_minimum_paired_scenarios=(
                value.formal_95_percent_rank_minimum_paired_scenarios
            ),
        )
    except (AttributeError, TypeError, ValueError) as error:
        raise CrossFamilyCalibrationInputError("paired calibration config is invalid") from error


def _preference(delta: float) -> CalibratedPreference:
    if not math.isfinite(delta):
        raise CrossFamilyCalibrationNumericalError("paired score difference is not finite")
    tolerance = 8.0 * math.ulp(max(1.0, abs(delta)))
    if abs(delta) <= tolerance:
        return "exact-tie"
    return "catalogue-orbit" if delta > 0.0 else "radio-polynomial"


def _lower_is_better(catalogue: float, radio: float) -> CalibratedPreference:
    tolerance = 8.0 * math.ulp(max(1.0, abs(catalogue), abs(radio)))
    if abs(catalogue - radio) <= tolerance:
        return "exact-tie"
    return "catalogue-orbit" if catalogue < radio else "radio-polynomial"


def _finite_difference(left: float, right: float, label: str) -> float:
    if not math.isfinite(left) or not math.isfinite(right):
        raise CrossFamilyCalibrationNumericalError(f"{label} inputs are not finite")
    result = left - right
    if not math.isfinite(result):
        raise CrossFamilyCalibrationNumericalError(f"{label} is not representable")
    return result


def _is_digest(value: str) -> bool:
    if not isinstance(value, str) or not value.startswith(_SHA256_PREFIX):
        return False
    suffix = value[len(_SHA256_PREFIX) :]
    return len(suffix) == _SHA256_HEX_LENGTH and all(item in "0123456789abcdef" for item in suffix)


__all__ = [
    "CrossFamilyCalibrationConfig",
    "CrossFamilyCalibrationInputError",
    "CrossFamilyCalibrationNumericalError",
    "CrossFamilyKnownTruthCase",
    "CrossFamilyKnownTruthCaseScore",
    "CrossFamilyPredictiveCalibrationAudit",
    "CrossFamilyScenarioDiagnostic",
    "audit_known_truth_cross_family_prediction",
]
