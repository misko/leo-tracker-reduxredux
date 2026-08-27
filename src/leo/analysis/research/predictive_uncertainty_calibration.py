"""Known-truth calibration of a uniform predictive-covariance scale.

This module calibrates one deliberately narrow diagnostic: a scalar multiplier
on an already-frozen Gaussian predictive covariance.  Calibration cases are
grouped into response-free scenarios; cases are averaged within scenario and
scenarios receive equal weight.  Leave-one-scenario-out rows expose whether a
scale learned elsewhere improves predictive consistency.

The scalar cannot repair a wrong covariance shape, missing nuisance state, or
catalogue-selection multiplicity.  The result therefore makes no coverage,
posterior-probability, model-selection, or identity claim.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

from leo.analysis.research.predictive_evidence_diagnostics import (
    PredictiveEvidenceModelSummary,
    PredictiveModelKind,
)

_INDEPENDENCE_ATTESTATION = "scenario-groups-frozen-response-free-and-independent-v1"
_SHA256_PREFIX = "sha256:"
_SHA256_HEX_LENGTH = 64


class PredictiveCalibrationInputError(ValueError):
    """The calibration inventory or score decomposition is invalid."""


class PredictiveCalibrationNumericalError(ValueError):
    """A covariance-scale operation is not numerically representable."""


@dataclass(frozen=True, slots=True)
class PredictiveCalibrationCase:
    """One known-truth score assigned to one independent scenario group."""

    case_id: str
    scenario_id: str
    evidence_digest: str
    truth_digest: str
    model_configuration_digest: str
    score: PredictiveEvidenceModelSummary


@dataclass(frozen=True, slots=True)
class PredictiveCalibrationConfig:
    model_kind: PredictiveModelKind
    model_configuration_digest: str
    expected_case_ids: tuple[str, ...]
    independence_attestation: Literal["scenario-groups-frozen-response-free-and-independent-v1"]
    minimum_scenarios_for_leave_one_out: int = 3
    formal_95_percent_rank_coverage_minimum_scenarios: int = 19

    def __post_init__(self) -> None:
        if not _is_digest(self.model_configuration_digest):
            raise PredictiveCalibrationInputError("model configuration must be digest-bound")
        if not self.expected_case_ids or len(set(self.expected_case_ids)) != len(
            self.expected_case_ids
        ):
            raise PredictiveCalibrationInputError("expected calibration cases must be unique")
        if any(not item.strip() for item in self.expected_case_ids):
            raise PredictiveCalibrationInputError("calibration case identities cannot be empty")
        if self.independence_attestation != _INDEPENDENCE_ATTESTATION:
            raise PredictiveCalibrationInputError(
                "calibration scenarios need the frozen independence attestation"
            )
        if self.minimum_scenarios_for_leave_one_out < 3:
            raise PredictiveCalibrationInputError(
                "leave-one-scenario-out calibration requires at least three scenarios"
            )
        if self.formal_95_percent_rank_coverage_minimum_scenarios < 19:
            raise PredictiveCalibrationInputError(
                "finite 95 percent rank coverage needs at least 19 independent scenarios"
            )


@dataclass(frozen=True, slots=True)
class PredictiveScenarioCalibrationDiagnostic:
    scenario_id: str
    case_count: int
    observation_count: int
    raw_scenario_mean_normalized_innovation_squared: float
    leave_one_scenario_out_variance_scale: float
    leave_one_scenario_out_calibrated_mean_normalized_innovation_squared: float
    unscaled_predictive_negative_log_likelihood: float
    leave_one_scenario_out_scaled_predictive_negative_log_likelihood: float
    scaled_minus_unscaled_predictive_negative_log_likelihood: float


@dataclass(frozen=True, slots=True)
class PredictiveCovarianceScaleCalibration:
    model_kind: PredictiveModelKind
    model_configuration_digest: str
    calibration_case_ids: tuple[str, ...]
    calibration_evidence_digests: tuple[str, ...]
    calibration_truth_digests: tuple[str, ...]
    scenario_ids: tuple[str, ...]
    case_count: int
    scenario_count: int
    observation_count: int
    scenario_equal_variance_scale: float
    scenario_equal_standard_deviation_scale: float
    observation_pooled_variance_scale: float
    scenario_diagnostics: tuple[PredictiveScenarioCalibrationDiagnostic, ...]
    formal_95_percent_rank_coverage_minimum_scenarios: int
    formal_95_percent_rank_coverage_scenario_count_sufficient: bool
    algorithm_version: Literal["known-truth-uniform-covariance-scale-calibration-v1"] = field(
        default="known-truth-uniform-covariance-scale-calibration-v1", init=False
    )
    scenario_equal_primary: Literal[True] = field(default=True, init=False)
    leave_one_scenario_out_diagnostic: Literal[True] = field(default=True, init=False)
    covariance_shape_changed: Literal[False] = field(default=False, init=False)
    covariance_shape_calibrated: Literal[False] = field(default=False, init=False)
    formal_coverage_claimed: Literal[False] = field(default=False, init=False)
    posterior_probability_produced: Literal[False] = field(default=False, init=False)
    model_selection_gate_produced: Literal[False] = field(default=False, init=False)
    identity_claimed: Literal[False] = field(default=False, init=False)


@dataclass(frozen=True, slots=True)
class AppliedPredictiveCovarianceScale:
    target_group_id: str
    target_evidence_digest: str
    model_kind: PredictiveModelKind
    model_configuration_digest: str
    observation_count: int
    variance_scale: float
    standard_deviation_scale: float
    unscaled_mean_normalized_innovation_squared: float
    scaled_mean_normalized_innovation_squared: float
    unscaled_log_determinant_covariance: float
    scaled_log_determinant_covariance: float
    unscaled_predictive_negative_log_likelihood: float
    scaled_predictive_negative_log_likelihood: float
    scaled_minus_unscaled_predictive_negative_log_likelihood: float
    target_excluded_from_calibration_cases: Literal[True] = field(default=True, init=False)
    covariance_shape_changed: Literal[False] = field(default=False, init=False)
    posterior_probability_produced: Literal[False] = field(default=False, init=False)
    model_selection_gate_produced: Literal[False] = field(default=False, init=False)


def calibrate_uniform_predictive_covariance(
    cases: tuple[PredictiveCalibrationCase, ...],
    config: PredictiveCalibrationConfig,
) -> PredictiveCovarianceScaleCalibration:
    """Fit a scenario-equal scale and compute leave-one-scenario-out diagnostics."""

    config = _revalidate_config(config)
    cases = tuple(_revalidate_case(item) for item in cases)
    if tuple(item.case_id for item in cases) != config.expected_case_ids:
        raise PredictiveCalibrationInputError(
            "calibration case inventory differs from the frozen configuration"
        )
    if any(item.score.model_kind != config.model_kind for item in cases):
        raise PredictiveCalibrationInputError("calibration model families differ")
    if any(item.model_configuration_digest != config.model_configuration_digest for item in cases):
        raise PredictiveCalibrationInputError("calibration model configurations differ")
    if len({item.evidence_digest for item in cases}) != len(cases):
        raise PredictiveCalibrationInputError("calibration evidence must not be duplicated")
    scenario_ids = tuple(sorted({item.scenario_id for item in cases}))
    if len(scenario_ids) < config.minimum_scenarios_for_leave_one_out:
        raise PredictiveCalibrationInputError("too few independent scenarios for leave-one-out")
    by_scenario = {
        scenario_id: tuple(item for item in cases if item.scenario_id == scenario_id)
        for scenario_id in scenario_ids
    }
    scenario_raw_nis = {
        scenario_id: _finite_mean(
            tuple(item.score.mean_normalized_innovation_squared for item in scenario_cases),
            "scenario normalized innovation",
        )
        for scenario_id, scenario_cases in by_scenario.items()
    }
    primary_scale = _finite_mean(
        tuple(scenario_raw_nis.values()),
        "scenario-equal variance scale",
    )
    pooled_scale = _finite_sum(
        tuple(item.score.mahalanobis_squared for item in cases),
        "pooled innovation quadratic",
    ) / _finite_sum(
        tuple(float(item.score.observation_count) for item in cases),
        "pooled observation count",
    )
    _require_positive_scale(primary_scale, "scenario-equal variance scale")
    _require_positive_scale(pooled_scale, "observation-pooled variance scale")
    diagnostics: list[PredictiveScenarioCalibrationDiagnostic] = []
    for scenario_id in scenario_ids:
        scenario_cases = by_scenario[scenario_id]
        training_scale = _finite_mean(
            tuple(value for other_id, value in scenario_raw_nis.items() if other_id != scenario_id),
            "leave-one-scenario-out variance scale",
        )
        _require_positive_scale(training_scale, "leave-one-scenario-out variance scale")
        unscaled_nll = _finite_sum(
            tuple(item.score.total_predictive_negative_log_likelihood for item in scenario_cases),
            "scenario unscaled predictive score",
        )
        scaled_nll = _finite_sum(
            tuple(_scaled_nll(item.score, training_scale) for item in scenario_cases),
            "scenario scaled predictive score",
        )
        diagnostics.append(
            PredictiveScenarioCalibrationDiagnostic(
                scenario_id=scenario_id,
                case_count=len(scenario_cases),
                observation_count=sum(item.score.observation_count for item in scenario_cases),
                raw_scenario_mean_normalized_innovation_squared=scenario_raw_nis[scenario_id],
                leave_one_scenario_out_variance_scale=training_scale,
                leave_one_scenario_out_calibrated_mean_normalized_innovation_squared=(
                    scenario_raw_nis[scenario_id] / training_scale
                ),
                unscaled_predictive_negative_log_likelihood=unscaled_nll,
                leave_one_scenario_out_scaled_predictive_negative_log_likelihood=scaled_nll,
                scaled_minus_unscaled_predictive_negative_log_likelihood=(
                    scaled_nll - unscaled_nll
                ),
            )
        )
    return PredictiveCovarianceScaleCalibration(
        model_kind=config.model_kind,
        model_configuration_digest=config.model_configuration_digest,
        calibration_case_ids=tuple(item.case_id for item in cases),
        calibration_evidence_digests=tuple(item.evidence_digest for item in cases),
        calibration_truth_digests=tuple(item.truth_digest for item in cases),
        scenario_ids=scenario_ids,
        case_count=len(cases),
        scenario_count=len(scenario_ids),
        observation_count=sum(item.score.observation_count for item in cases),
        scenario_equal_variance_scale=primary_scale,
        scenario_equal_standard_deviation_scale=math.sqrt(primary_scale),
        observation_pooled_variance_scale=pooled_scale,
        scenario_diagnostics=tuple(diagnostics),
        formal_95_percent_rank_coverage_minimum_scenarios=(
            config.formal_95_percent_rank_coverage_minimum_scenarios
        ),
        formal_95_percent_rank_coverage_scenario_count_sufficient=(
            len(scenario_ids) >= config.formal_95_percent_rank_coverage_minimum_scenarios
        ),
    )


def apply_uniform_predictive_covariance_scale(
    score: PredictiveEvidenceModelSummary,
    calibration: PredictiveCovarianceScaleCalibration,
    *,
    target_group_id: str,
    target_evidence_digest: str,
    model_configuration_digest: str,
) -> AppliedPredictiveCovarianceScale:
    """Apply a previously learned scale to one excluded target score."""

    score = _revalidate_score(score)
    calibration = _revalidate_calibration(calibration)
    if not target_group_id.strip():
        raise PredictiveCalibrationInputError("target group identity cannot be empty")
    if not _is_digest(target_evidence_digest):
        raise PredictiveCalibrationInputError("target evidence must be digest-bound")
    if (
        target_group_id
        in (
            *calibration.calibration_case_ids,
            *calibration.scenario_ids,
        )
        or target_evidence_digest in calibration.calibration_evidence_digests
    ):
        raise PredictiveCalibrationInputError("target group was used during calibration")
    if score.model_kind != calibration.model_kind:
        raise PredictiveCalibrationInputError("target and calibration model families differ")
    if model_configuration_digest != calibration.model_configuration_digest:
        raise PredictiveCalibrationInputError("target model configuration differs")
    scaled_logdet = score.log_determinant_covariance + score.observation_count * math.log(
        calibration.scenario_equal_variance_scale
    )
    scaled_nll = _scaled_nll(score, calibration.scenario_equal_variance_scale)
    return AppliedPredictiveCovarianceScale(
        target_group_id=target_group_id,
        target_evidence_digest=target_evidence_digest,
        model_kind=score.model_kind,
        model_configuration_digest=model_configuration_digest,
        observation_count=score.observation_count,
        variance_scale=calibration.scenario_equal_variance_scale,
        standard_deviation_scale=calibration.scenario_equal_standard_deviation_scale,
        unscaled_mean_normalized_innovation_squared=(score.mean_normalized_innovation_squared),
        scaled_mean_normalized_innovation_squared=(
            score.mean_normalized_innovation_squared / calibration.scenario_equal_variance_scale
        ),
        unscaled_log_determinant_covariance=score.log_determinant_covariance,
        scaled_log_determinant_covariance=scaled_logdet,
        unscaled_predictive_negative_log_likelihood=(
            score.total_predictive_negative_log_likelihood
        ),
        scaled_predictive_negative_log_likelihood=scaled_nll,
        scaled_minus_unscaled_predictive_negative_log_likelihood=(
            scaled_nll - score.total_predictive_negative_log_likelihood
        ),
    )


def _scaled_nll(score: PredictiveEvidenceModelSummary, variance_scale: float) -> float:
    _require_positive_scale(variance_scale, "predictive variance scale")
    try:
        terms = (
            score.mahalanobis_squared / variance_scale,
            score.log_determinant_covariance,
            score.observation_count * math.log(variance_scale),
            score.observation_count * math.log(2.0 * math.pi),
        )
        if any(not math.isfinite(item) for item in terms):
            raise ValueError("scaled predictive term is not finite")
        value = 0.5 * math.fsum(terms)
    except (OverflowError, ValueError) as error:
        raise PredictiveCalibrationNumericalError(
            "scaled predictive score is not representable"
        ) from error
    if not math.isfinite(value):
        raise PredictiveCalibrationNumericalError("scaled predictive score is not finite")
    return value


def _revalidate_case(value: PredictiveCalibrationCase) -> PredictiveCalibrationCase:
    try:
        if not value.case_id.strip() or not value.scenario_id.strip():
            raise ValueError("case and scenario identities cannot be empty")
        if (
            not _is_digest(value.evidence_digest)
            or not _is_digest(value.truth_digest)
            or not _is_digest(value.model_configuration_digest)
        ):
            raise ValueError("calibration authorities must be digest-bound")
        return PredictiveCalibrationCase(
            case_id=value.case_id,
            scenario_id=value.scenario_id,
            evidence_digest=value.evidence_digest,
            truth_digest=value.truth_digest,
            model_configuration_digest=value.model_configuration_digest,
            score=_revalidate_score(value.score),
        )
    except PredictiveCalibrationInputError:
        raise
    except (AttributeError, TypeError, ValueError) as error:
        raise PredictiveCalibrationInputError("predictive calibration case is invalid") from error


def _revalidate_score(value: PredictiveEvidenceModelSummary) -> PredictiveEvidenceModelSummary:
    try:
        copied = PredictiveEvidenceModelSummary(
            **{
                name: getattr(value, name)
                for name in PredictiveEvidenceModelSummary.__dataclass_fields__
            }
        )
    except (AttributeError, TypeError, ValueError) as error:
        raise PredictiveCalibrationInputError("predictive score summary is invalid") from error
    values = (
        copied.future_residual_rms_hz,
        copied.mahalanobis_squared,
        copied.mean_normalized_innovation_squared,
        copied.log_determinant_covariance,
        copied.geometric_mean_predictive_standard_uncertainty_hz,
        copied.residual_fit_negative_log_likelihood_component,
        copied.uncertainty_volume_negative_log_likelihood_component,
        copied.gaussian_normalization_negative_log_likelihood_component,
        copied.total_predictive_negative_log_likelihood,
        copied.predictive_negative_log_likelihood_per_observation,
    )
    if any(not math.isfinite(item) for item in values):
        raise PredictiveCalibrationInputError("predictive score summary is not finite")
    if (
        copied.observation_count < 1
        or copied.mahalanobis_squared < 0.0
        or copied.future_residual_rms_hz < 0.0
        or copied.geometric_mean_predictive_standard_uncertainty_hz <= 0.0
        or copied.fitted_continuous_parameter_count < 1
        or copied.profiled_discrete_state_count < 1
        or copied.training_search_family_size < 1
    ):
        raise PredictiveCalibrationInputError("predictive score counts or quadratic are invalid")
    expected_nis = copied.mahalanobis_squared / copied.observation_count
    expected_residual_component = 0.5 * copied.mahalanobis_squared
    expected_uncertainty_component = 0.5 * copied.log_determinant_covariance
    expected_normalization_component = 0.5 * copied.observation_count * math.log(2.0 * math.pi)
    expected_nll = (
        expected_residual_component
        + expected_uncertainty_component
        + expected_normalization_component
    )
    try:
        expected_geometric_sigma = math.exp(
            copied.log_determinant_covariance / (2.0 * copied.observation_count)
        )
    except OverflowError as error:
        raise PredictiveCalibrationInputError(
            "predictive geometric uncertainty is not representable"
        ) from error
    expected_direction = (
        "equal-one-within-float"
        if abs(expected_nis - 1.0) <= 8.0 * math.ulp(max(1.0, abs(expected_nis)))
        else "below-one"
        if expected_nis < 1.0
        else "above-one"
    )
    if (
        not math.isclose(
            copied.mean_normalized_innovation_squared,
            expected_nis,
            rel_tol=1e-12,
            abs_tol=1e-12,
        )
        or any(
            not math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-9)
            for actual, expected in (
                (
                    copied.residual_fit_negative_log_likelihood_component,
                    expected_residual_component,
                ),
                (
                    copied.uncertainty_volume_negative_log_likelihood_component,
                    expected_uncertainty_component,
                ),
                (
                    copied.gaussian_normalization_negative_log_likelihood_component,
                    expected_normalization_component,
                ),
                (copied.total_predictive_negative_log_likelihood, expected_nll),
                (
                    copied.predictive_negative_log_likelihood_per_observation,
                    expected_nll / copied.observation_count,
                ),
                (
                    copied.geometric_mean_predictive_standard_uncertainty_hz,
                    expected_geometric_sigma,
                ),
            )
        )
        or copied.nis_direction != expected_direction
    ):
        raise PredictiveCalibrationInputError("predictive score decomposition is inconsistent")
    return copied


def _revalidate_config(value: PredictiveCalibrationConfig) -> PredictiveCalibrationConfig:
    try:
        return PredictiveCalibrationConfig(
            model_kind=value.model_kind,
            model_configuration_digest=value.model_configuration_digest,
            expected_case_ids=tuple(value.expected_case_ids),
            independence_attestation=value.independence_attestation,
            minimum_scenarios_for_leave_one_out=value.minimum_scenarios_for_leave_one_out,
            formal_95_percent_rank_coverage_minimum_scenarios=(
                value.formal_95_percent_rank_coverage_minimum_scenarios
            ),
        )
    except (AttributeError, TypeError, ValueError) as error:
        raise PredictiveCalibrationInputError("predictive calibration config is invalid") from error


def _revalidate_calibration(
    value: PredictiveCovarianceScaleCalibration,
) -> PredictiveCovarianceScaleCalibration:
    try:
        copied = PredictiveCovarianceScaleCalibration(
            **{
                name: getattr(value, name)
                for name, item in PredictiveCovarianceScaleCalibration.__dataclass_fields__.items()
                if item.init
            }
        )
    except (AttributeError, TypeError, ValueError) as error:
        raise PredictiveCalibrationInputError("predictive calibration result is invalid") from error
    _require_positive_scale(copied.scenario_equal_variance_scale, "calibrated variance scale")
    _require_positive_scale(copied.observation_pooled_variance_scale, "pooled variance scale")
    if copied.observation_count < 1:
        raise PredictiveCalibrationInputError("calibration observation count is invalid")
    if not math.isclose(
        copied.scenario_equal_standard_deviation_scale**2,
        copied.scenario_equal_variance_scale,
        rel_tol=1e-12,
        abs_tol=1e-12,
    ):
        raise PredictiveCalibrationInputError("calibrated variance and deviation scales differ")
    if copied.case_count != len(copied.calibration_case_ids):
        raise PredictiveCalibrationInputError("calibration case count is inconsistent")
    if copied.case_count != len(copied.calibration_evidence_digests) or copied.case_count != len(
        copied.calibration_truth_digests
    ):
        raise PredictiveCalibrationInputError("calibration authority count is inconsistent")
    if (
        len(set(copied.calibration_case_ids)) != copied.case_count
        or len(set(copied.calibration_evidence_digests)) != copied.case_count
        or any(not _is_digest(item) for item in copied.calibration_evidence_digests)
        or any(not _is_digest(item) for item in copied.calibration_truth_digests)
    ):
        raise PredictiveCalibrationInputError("calibration authority inventory is invalid")
    if copied.scenario_count != len(copied.scenario_ids):
        raise PredictiveCalibrationInputError("calibration scenario count is inconsistent")
    if copied.scenario_ids != tuple(sorted(set(copied.scenario_ids))):
        raise PredictiveCalibrationInputError("calibration scenarios are not canonical")
    if (
        copied.scenario_count != len(copied.scenario_diagnostics)
        or tuple(item.scenario_id for item in copied.scenario_diagnostics) != copied.scenario_ids
    ):
        raise PredictiveCalibrationInputError("calibration scenario diagnostics are incomplete")
    if (
        sum(item.case_count for item in copied.scenario_diagnostics) != copied.case_count
        or sum(item.observation_count for item in copied.scenario_diagnostics)
        != copied.observation_count
    ):
        raise PredictiveCalibrationInputError("calibration diagnostic counts are inconsistent")
    if not math.isclose(
        _finite_mean(
            tuple(
                item.raw_scenario_mean_normalized_innovation_squared
                for item in copied.scenario_diagnostics
            ),
            "persisted scenario-equal variance scale",
        ),
        copied.scenario_equal_variance_scale,
        rel_tol=1e-12,
        abs_tol=1e-12,
    ):
        raise PredictiveCalibrationInputError("scenario-equal calibration scale is inconsistent")
    for item in copied.scenario_diagnostics:
        values = (
            item.raw_scenario_mean_normalized_innovation_squared,
            item.leave_one_scenario_out_variance_scale,
            item.leave_one_scenario_out_calibrated_mean_normalized_innovation_squared,
            item.unscaled_predictive_negative_log_likelihood,
            item.leave_one_scenario_out_scaled_predictive_negative_log_likelihood,
            item.scaled_minus_unscaled_predictive_negative_log_likelihood,
        )
        if (
            item.case_count < 1
            or item.observation_count < 1
            or any(not math.isfinite(number) for number in values)
        ):
            raise PredictiveCalibrationInputError("calibration scenario diagnostic is invalid")
        if (
            item.leave_one_scenario_out_variance_scale <= 0.0
            or not math.isclose(
                item.leave_one_scenario_out_calibrated_mean_normalized_innovation_squared,
                item.raw_scenario_mean_normalized_innovation_squared
                / item.leave_one_scenario_out_variance_scale,
                rel_tol=1e-12,
                abs_tol=1e-12,
            )
            or not math.isclose(
                item.scaled_minus_unscaled_predictive_negative_log_likelihood,
                item.leave_one_scenario_out_scaled_predictive_negative_log_likelihood
                - item.unscaled_predictive_negative_log_likelihood,
                rel_tol=1e-12,
                abs_tol=1e-9,
            )
        ):
            raise PredictiveCalibrationInputError(
                "calibration scenario diagnostic decomposition is inconsistent"
            )
    if (
        copied.formal_95_percent_rank_coverage_minimum_scenarios < 19
        or copied.formal_95_percent_rank_coverage_scenario_count_sufficient
        != (copied.scenario_count >= copied.formal_95_percent_rank_coverage_minimum_scenarios)
    ):
        raise PredictiveCalibrationInputError("formal coverage-count diagnostic is inconsistent")
    return copied


def _require_positive_scale(value: float, label: str) -> None:
    if not math.isfinite(value) or value <= 0.0:
        raise PredictiveCalibrationNumericalError(f"{label} must be finite and positive")


def _finite_sum(values: tuple[float, ...], label: str) -> float:
    if not values or any(not math.isfinite(item) for item in values):
        raise PredictiveCalibrationNumericalError(f"{label} inputs must be finite and non-empty")
    try:
        result = math.fsum(values)
    except (OverflowError, ValueError) as error:
        raise PredictiveCalibrationNumericalError(f"{label} is not representable") from error
    if not math.isfinite(result):
        raise PredictiveCalibrationNumericalError(f"{label} is not finite")
    return result


def _finite_mean(values: tuple[float, ...], label: str) -> float:
    return _finite_sum(values, label) / len(values)


def _is_digest(value: str) -> bool:
    if not isinstance(value, str) or not value.startswith(_SHA256_PREFIX):
        return False
    suffix = value[len(_SHA256_PREFIX) :]
    return len(suffix) == _SHA256_HEX_LENGTH and all(item in "0123456789abcdef" for item in suffix)


__all__ = [
    "AppliedPredictiveCovarianceScale",
    "PredictiveCalibrationCase",
    "PredictiveCalibrationConfig",
    "PredictiveCalibrationInputError",
    "PredictiveCalibrationNumericalError",
    "PredictiveCovarianceScaleCalibration",
    "PredictiveScenarioCalibrationDiagnostic",
    "apply_uniform_predictive_covariance_scale",
    "calibrate_uniform_predictive_covariance",
]
