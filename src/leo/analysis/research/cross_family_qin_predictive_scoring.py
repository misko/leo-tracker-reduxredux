"""Paired known-truth catalogue-versus-radio predictive scoring.

The scorer consumes only the sealed paired Qin evidence and its frozen protocol.
For each truth arm it fits a constant offset around the response-free TLE curve
and degree-1/2/3 radio polynomials on even-Qin training rows, then evaluates the
models once on the identical odd-Qin future rows.  Gaussian predictive
covariance includes both persisted measurement uncertainty and training-fit
parameter covariance.

Uniform covariance scales are estimated independently for the two model
families with leave-one-background-pair-out diagnostics.  Three pairs are only
enough for a mechanistic development diagnostic: this module fits no threshold,
posterior odds, identity gate, or positioning claim.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal, cast

from leo.analysis.research.predictive_evidence_diagnostics import (
    CatalogueRadioPredictiveEvidenceAudit,
    CatalogueRadioPredictiveEvidenceComparison,
    EvidenceDiagnostic,
    NisDirection,
    PredictiveEvidenceModelSummary,
    ScorePreference,
)
from leo.analysis.research.predictive_uncertainty_calibration import (
    PredictiveCalibrationCase,
    PredictiveCalibrationConfig,
    PredictiveCovarianceScaleCalibration,
    calibrate_uniform_predictive_covariance,
)
from leo.contracts.digests import canonical_digest

type TruthFamily = Literal["catalogue-orbit", "radio-polynomial"]
type ModelPreference = Literal["catalogue-orbit", "radio-polynomial", "exact-tie"]

_SCHEMA = "org.leo.research.satellite-pnt-cross-family-predictive-scoring/v1"
_EVIDENCE_SCHEMA = "org.leo.research.satellite-pnt-cross-family-injection-evidence/v1"
_INDEPENDENCE: Literal["scenario-groups-frozen-response-free-and-independent-v1"] = (
    "scenario-groups-frozen-response-free-and-independent-v1"
)


class CrossFamilyQinScoringInputError(ValueError):
    """The frozen scoring design or paired evidence fails closed."""


class CrossFamilyQinScoringNumericalError(ValueError):
    """A weighted fit or predictive density is not numerically trustworthy."""


@dataclass(frozen=True, slots=True)
class CrossFamilyQinScoringConfig:
    evidence_path: str
    evidence_sha256: str
    protocol_path: str
    protocol_sha256: str
    independent_background_pair_count: int
    truth_arm_count: int
    primary_degree: Literal[1]
    diagnostic_degrees: tuple[Literal[2], Literal[3]]
    additional_variance_floor_hz2: float
    minimum_independent_pairs: int
    formal_95_percent_rank_minimum_pairs: int
    result_path: str
    report_path: str
    config_digest: str


@dataclass(frozen=True, slots=True)
class ModelFitReceipt:
    model_kind: Literal["catalogue-orbit", "radio-polynomial"]
    degree: int
    reference_time_s: float
    coefficients_hz: tuple[float, ...]
    coefficient_covariance: tuple[tuple[float, ...], ...]
    training_observation_count: int
    future_observation_count: int
    summary: PredictiveEvidenceModelSummary
    training_response_accessed: Literal[True] = field(default=True, init=False)
    future_response_used_for_fit: Literal[False] = field(default=False, init=False)


@dataclass(frozen=True, slots=True)
class PairedQinCaseScore:
    case_id: str
    scenario_id: str
    truth_model_family: TruthFamily
    evidence_digest: str
    truth_digest: str
    catalogue_configuration_digest: str
    radio_configuration_digest: str
    catalogue_fit: ModelFitReceipt
    radio_fits: tuple[ModelFitReceipt, ...]
    audit: CatalogueRadioPredictiveEvidenceAudit


@dataclass(frozen=True, slots=True)
class LeaveOnePairOutCaseDiagnostic:
    case_id: str
    scenario_id: str
    truth_model_family: TruthFamily
    observation_count: int
    catalogue_variance_scale_from_other_pairs: float
    radio_variance_scale_from_other_pairs: float
    catalogue_scaled_predictive_negative_log_likelihood: float
    radio_scaled_predictive_negative_log_likelihood: float
    radio_minus_catalogue_scaled_predictive_negative_log_likelihood: float
    preference: ModelPreference
    preference_matches_truth: bool


@dataclass(frozen=True, slots=True)
class CrossFamilyQinPredictiveScoringResult:
    config_digest: str
    evidence_sha256: str
    protocol_sha256: str
    catalogue_configuration_digest: str
    radio_configuration_digest: str
    cases: tuple[PairedQinCaseScore, ...]
    catalogue_calibration: PredictiveCovarianceScaleCalibration
    radio_calibration: PredictiveCovarianceScaleCalibration
    leave_one_pair_out_diagnostics: tuple[LeaveOnePairOutCaseDiagnostic, ...]
    independent_background_pair_count: int
    truth_arm_count: int
    correct_truth_arm_count: int
    tied_truth_arm_count: int
    truth_arm_equal_accuracy: float
    formal_95_percent_rank_minimum_pairs: int
    formal_95_percent_rank_pair_count_sufficient: bool
    result_digest: str
    algorithm_version: Literal["paired-qin-cross-family-predictive-scoring-v1"] = field(
        default="paired-qin-cross-family-predictive-scoring-v1", init=False
    )
    leave_one_background_pair_out: Literal[True] = field(default=True, init=False)
    threshold_fitted: Literal[False] = field(default=False, init=False)
    posterior_odds_produced: Literal[False] = field(default=False, init=False)
    full_catalogue_multiplicity_modeled: Literal[False] = field(default=False, init=False)
    identity_claimed: Literal[False] = field(default=False, init=False)
    positioning_validated: Literal[False] = field(default=False, init=False)


def load_cross_family_qin_scoring_config(path: Path) -> CrossFamilyQinScoringConfig:
    """Load the exact frozen scoring design."""

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CrossFamilyQinScoringInputError("predictive scoring config is unreadable") from error
    if not isinstance(raw, dict) or raw.get("schema") != _SCHEMA:
        raise CrossFamilyQinScoringInputError("predictive scoring config schema differs")
    try:
        input_value = cast(dict[str, Any], raw["input"])
        partition = cast(dict[str, Any], raw["partition"])
        catalogue = cast(dict[str, Any], raw["catalogue_model"])
        radio = cast(dict[str, Any], raw["radio_model"])
        likelihood = cast(dict[str, Any], raw["predictive_likelihood"])
        calibration = cast(dict[str, Any], raw["calibration"])
        outputs = cast(dict[str, Any], raw["outputs"])
        claims = cast(dict[str, Any], raw["claims"])
    except (KeyError, TypeError) as error:
        raise CrossFamilyQinScoringInputError("predictive scoring config is incomplete") from error
    expected_literals = (
        raw.get("status") == "frozen-opened-development",
        partition.get("training") == "first-60-percent-even-qin",
        partition.get("future") == "final-40-percent-odd-qin",
        partition.get("selection_or_fit_uses_future_response") is False,
        partition.get("identical_future_rows_across_model_families") is True,
        partition.get("no_result_rows_retained") is True,
        catalogue.get("curve") == "frozen-true-causal-tle-orbit-trajectory",
        catalogue.get("tau_s") == 0.0,
        catalogue.get("candidate_search_count") == 1,
        catalogue.get("training_nuisance") == "one-constant-cfo-offset",
        catalogue.get("candidate_specific_rate_or_acceleration_forbidden") is True,
        radio.get("family") == "support-time-polynomial",
        radio.get("primary_degree") == 1,
        radio.get("diagnostic_degrees") == [2, 3],
        radio.get("training_only_fit") is True,
        likelihood.get("family") == "gaussian-training-posterior-predictive",
        likelihood.get("measurement_variance") == "persisted-qin-standard-uncertainty-squared",
        likelihood.get("parameter_covariance") == "weighted-least-squares-normal-matrix-inverse",
        likelihood.get("future_covariance") == "measurement-diagonal-plus-parameter-covariance",
        likelihood.get("row_weighting") == "one-per-usable-frame",
        calibration.get("method") == "leave-one-background-pair-out-uniform-variance-scale",
        calibration.get("scenario_weighting") == "background-pair-equal",
        calibration.get("truth_arms_jointly_define_each_scenario_scale") is True,
        calibration.get("formal_coverage_claimed") is False,
        claims
        == {
            "threshold_fitted": False,
            "posterior_odds_produced": False,
            "full_catalogue_multiplicity_modeled": False,
            "satellite_identity_claimed": False,
            "positioning_validated": False,
        },
    )
    if not all(expected_literals):
        raise CrossFamilyQinScoringInputError("predictive scoring semantics differ")
    floor = likelihood.get("additional_variance_floor_hz2")
    if not isinstance(floor, (int, float)) or not math.isfinite(float(floor)) or float(floor) < 0:
        raise CrossFamilyQinScoringInputError("predictive variance floor is invalid")
    pair_count = input_value.get("independent_background_pair_count")
    arm_count = input_value.get("truth_arm_count")
    minimum_pairs = calibration.get("minimum_independent_pairs")
    formal_pairs = calibration.get("formal_95_percent_rank_minimum_pairs")
    if (
        not isinstance(pair_count, int)
        or pair_count < 3
        or arm_count != 2 * pair_count
        or not isinstance(minimum_pairs, int)
        or minimum_pairs < 3
        or not isinstance(formal_pairs, int)
        or formal_pairs < 19
    ):
        raise CrossFamilyQinScoringInputError("predictive scoring counts are invalid")
    strings = (
        input_value.get("evidence_path"),
        input_value.get("evidence_sha256"),
        input_value.get("protocol_path"),
        input_value.get("protocol_sha256"),
        outputs.get("result_path"),
        outputs.get("report_path"),
    )
    if any(not isinstance(item, str) or not item for item in strings):
        raise CrossFamilyQinScoringInputError("predictive scoring paths or digests are invalid")
    if not _is_digest(cast(str, strings[1])) or not _is_digest(cast(str, strings[3])):
        raise CrossFamilyQinScoringInputError("predictive input hashes are invalid")
    return CrossFamilyQinScoringConfig(
        evidence_path=cast(str, strings[0]),
        evidence_sha256=cast(str, strings[1]),
        protocol_path=cast(str, strings[2]),
        protocol_sha256=cast(str, strings[3]),
        independent_background_pair_count=pair_count,
        truth_arm_count=cast(int, arm_count),
        primary_degree=1,
        diagnostic_degrees=(2, 3),
        additional_variance_floor_hz2=float(floor),
        minimum_independent_pairs=minimum_pairs,
        formal_95_percent_rank_minimum_pairs=formal_pairs,
        result_path=cast(str, strings[4]),
        report_path=cast(str, strings[5]),
        config_digest=canonical_digest(raw),
    )


def score_cross_family_qin_evidence(
    evidence_bytes: bytes,
    protocol_bytes: bytes,
    config: CrossFamilyQinScoringConfig,
) -> CrossFamilyQinPredictiveScoringResult:
    """Score both model families and produce leave-one-pair-out diagnostics."""

    config = _revalidate_config(config)
    if _sha256(evidence_bytes) != config.evidence_sha256:
        raise CrossFamilyQinScoringInputError("paired Qin evidence hash differs")
    if _sha256(protocol_bytes) != config.protocol_sha256:
        raise CrossFamilyQinScoringInputError("paired Qin protocol hash differs")
    evidence = _json_object(evidence_bytes, "paired Qin evidence")
    protocol = _json_object(protocol_bytes, "paired Qin protocol")
    _validate_evidence_envelope(evidence, protocol, config)
    catalogue_configuration_digest = canonical_digest(
        {
            "catalogue_model": "true-causal-tle-tau0-plus-training-offset-v1",
            "predictive_likelihood": "gaussian-training-posterior-predictive-v1",
            "additional_variance_floor_hz2": config.additional_variance_floor_hz2,
        }
    )
    radio_configuration_digest = canonical_digest(
        {
            "radio_model": "training-support-time-polynomial-v1",
            "degrees": [1, 2, 3],
            "predictive_likelihood": "gaussian-training-posterior-predictive-v1",
            "additional_variance_floor_hz2": config.additional_variance_floor_hz2,
        }
    )
    protocol_pairs = {item["pair_id"]: item for item in protocol["pairs"]}
    truth_receipts = {item["pair_id"]: item for item in evidence["truth_receipts"]}
    cases: list[PairedQinCaseScore] = []
    for pair in evidence["paired_evidence"]:
        pair_id = _required_string(pair, "pair_id")
        protocol_pair = protocol_pairs[pair_id]
        truth = truth_receipts[pair_id]
        _validate_pair_identity(pair, protocol_pair, truth)
        orbit_curve_rows = pair["orbit"]["observation_rows"]
        lane_families: tuple[tuple[str, TruthFamily], ...] = (
            ("orbit", "catalogue-orbit"),
            ("radio", "radio-polynomial"),
        )
        for lane, truth_family in lane_families:
            cases.append(
                _score_case(
                    pair_id=pair_id,
                    truth_family=truth_family,
                    arm=pair[lane],
                    orbit_curve_rows=orbit_curve_rows,
                    catalog_number=int(protocol_pair["true_catalog_number"]),
                    truth_digest=_required_digest(truth, "truth_digest"),
                    catalogue_configuration_digest=catalogue_configuration_digest,
                    radio_configuration_digest=radio_configuration_digest,
                    variance_floor_hz2=config.additional_variance_floor_hz2,
                )
            )
    ordered_cases = tuple(cases)
    if len(ordered_cases) != config.truth_arm_count:
        raise CrossFamilyQinScoringInputError("paired truth arm inventory differs")
    catalogue_calibration = calibrate_uniform_predictive_covariance(
        tuple(_calibration_case(item, "catalogue-orbit", config.primary_degree) for item in cases),
        PredictiveCalibrationConfig(
            model_kind="catalogue-orbit",
            model_configuration_digest=catalogue_configuration_digest,
            expected_case_ids=tuple(item.case_id for item in cases),
            independence_attestation=_INDEPENDENCE,
            minimum_scenarios_for_leave_one_out=config.minimum_independent_pairs,
            formal_95_percent_rank_coverage_minimum_scenarios=(
                config.formal_95_percent_rank_minimum_pairs
            ),
        ),
    )
    radio_calibration = calibrate_uniform_predictive_covariance(
        tuple(_calibration_case(item, "radio-polynomial", config.primary_degree) for item in cases),
        PredictiveCalibrationConfig(
            model_kind="radio-polynomial",
            model_configuration_digest=radio_configuration_digest,
            expected_case_ids=tuple(item.case_id for item in cases),
            independence_attestation=_INDEPENDENCE,
            minimum_scenarios_for_leave_one_out=config.minimum_independent_pairs,
            formal_95_percent_rank_coverage_minimum_scenarios=(
                config.formal_95_percent_rank_minimum_pairs
            ),
        ),
    )
    catalogue_scales = {
        item.scenario_id: item.leave_one_scenario_out_variance_scale
        for item in catalogue_calibration.scenario_diagnostics
    }
    radio_scales = {
        item.scenario_id: item.leave_one_scenario_out_variance_scale
        for item in radio_calibration.scenario_diagnostics
    }
    diagnostics = tuple(
        _leave_one_out_diagnostic(
            item,
            primary_degree=config.primary_degree,
            catalogue_scale=catalogue_scales[item.scenario_id],
            radio_scale=radio_scales[item.scenario_id],
        )
        for item in cases
    )
    correct = sum(item.preference_matches_truth for item in diagnostics)
    tied = sum(item.preference == "exact-tie" for item in diagnostics)
    payload = {
        "algorithm_version": "paired-qin-cross-family-predictive-scoring-v1",
        "config_digest": config.config_digest,
        "evidence_sha256": config.evidence_sha256,
        "protocol_sha256": config.protocol_sha256,
        "catalogue_configuration_digest": catalogue_configuration_digest,
        "radio_configuration_digest": radio_configuration_digest,
        "cases": [asdict(item) for item in ordered_cases],
        "catalogue_calibration": asdict(catalogue_calibration),
        "radio_calibration": asdict(radio_calibration),
        "leave_one_pair_out_diagnostics": [asdict(item) for item in diagnostics],
        "independent_background_pair_count": config.independent_background_pair_count,
        "truth_arm_count": config.truth_arm_count,
        "correct_truth_arm_count": correct,
        "tied_truth_arm_count": tied,
        "truth_arm_equal_accuracy": correct / config.truth_arm_count,
        "formal_95_percent_rank_minimum_pairs": config.formal_95_percent_rank_minimum_pairs,
        "formal_95_percent_rank_pair_count_sufficient": (
            config.independent_background_pair_count >= config.formal_95_percent_rank_minimum_pairs
        ),
        "leave_one_background_pair_out": True,
        "threshold_fitted": False,
        "posterior_odds_produced": False,
        "full_catalogue_multiplicity_modeled": False,
        "identity_claimed": False,
        "positioning_validated": False,
    }
    return CrossFamilyQinPredictiveScoringResult(
        config_digest=config.config_digest,
        evidence_sha256=config.evidence_sha256,
        protocol_sha256=config.protocol_sha256,
        catalogue_configuration_digest=catalogue_configuration_digest,
        radio_configuration_digest=radio_configuration_digest,
        cases=ordered_cases,
        catalogue_calibration=catalogue_calibration,
        radio_calibration=radio_calibration,
        leave_one_pair_out_diagnostics=diagnostics,
        independent_background_pair_count=config.independent_background_pair_count,
        truth_arm_count=config.truth_arm_count,
        correct_truth_arm_count=correct,
        tied_truth_arm_count=tied,
        truth_arm_equal_accuracy=correct / config.truth_arm_count,
        formal_95_percent_rank_minimum_pairs=config.formal_95_percent_rank_minimum_pairs,
        formal_95_percent_rank_pair_count_sufficient=(
            config.independent_background_pair_count >= config.formal_95_percent_rank_minimum_pairs
        ),
        result_digest=canonical_digest(payload),
    )


def _score_case(
    *,
    pair_id: str,
    truth_family: TruthFamily,
    arm: dict[str, Any],
    orbit_curve_rows: list[dict[str, Any]],
    catalog_number: int,
    truth_digest: str,
    catalogue_configuration_digest: str,
    radio_configuration_digest: str,
    variance_floor_hz2: float,
) -> PairedQinCaseScore:
    rows = arm.get("observation_rows")
    if not isinstance(rows, list) or not isinstance(orbit_curve_rows, list):
        raise CrossFamilyQinScoringInputError("paired arm rows are absent")
    if len(rows) != len(orbit_curve_rows) or not rows:
        raise CrossFamilyQinScoringInputError("paired arm row inventories differ")
    for measured, orbit in zip(rows, orbit_curve_rows, strict=True):
        identity = (
            measured.get("frame_index"),
            measured.get("reference_time_s"),
            measured.get("absolute_frame_start_sample"),
            measured.get("split"),
        )
        orbit_identity = (
            orbit.get("frame_index"),
            orbit.get("reference_time_s"),
            orbit.get("absolute_frame_start_sample"),
            orbit.get("split"),
        )
        if identity != orbit_identity:
            raise CrossFamilyQinScoringInputError("paired arm frame inventories differ")
    training = [
        item
        for item in rows
        if item.get("split") == "training-even-qin" and item.get("usable") is True
    ]
    future = [
        item
        for item in rows
        if item.get("split") == "future-odd-qin" and item.get("usable") is True
    ]
    if len(training) < 4 or len(future) < 1:
        raise CrossFamilyQinScoringInputError("paired arm has insufficient usable rows")
    orbit_by_frame = {int(item["frame_index"]): item for item in orbit_curve_rows}
    catalogue_fit = _fit_and_score(
        training,
        future,
        model_kind="catalogue-orbit",
        degree=0,
        base_prediction_by_frame={
            frame: _finite_float(item.get("truth_cfo_hz"), "orbit truth CFO")
            for frame, item in orbit_by_frame.items()
        },
        variance_floor_hz2=variance_floor_hz2,
    )
    radio_fits = tuple(
        _fit_and_score(
            training,
            future,
            model_kind="radio-polynomial",
            degree=degree,
            base_prediction_by_frame=None,
            variance_floor_hz2=variance_floor_hz2,
        )
        for degree in (1, 2, 3)
    )
    comparisons = tuple(
        _comparison(catalogue_fit.summary, fit.summary, degree=fit.degree) for fit in radio_fits
    )
    diagnostics: list[EvidenceDiagnostic] = [
        "cross-model-uncertainty-not-calibrated",
        "search-multiplicity-not-normalized",
    ]
    if any(item.preference_disagrees for item in comparisons):
        diagnostics.append("rms-and-nll-preference-disagree")
    diagnostics.sort()
    arm_digest = _required_digest(arm, "evidence_digest")
    case_id = f"{pair_id}:{truth_family}"
    training_ids = tuple(_observation_id(arm_digest, item) for item in training)
    future_ids = tuple(_observation_id(arm_digest, item) for item in future)
    audit = CatalogueRadioPredictiveEvidenceAudit(
        graph_content_digest=arm_digest,
        training_observation_ids=training_ids,
        evaluation_observation_ids=future_ids,
        catalogue_number=catalog_number,
        catalogue_training_rank=1,
        selected_tau_s=0.0,
        catalogue_candidate_search_count=1,
        catalogue_tau_state_count=1,
        comparisons=comparisons,
        diagnostics=tuple(diagnostics),
    )
    return PairedQinCaseScore(
        case_id=case_id,
        scenario_id=pair_id,
        truth_model_family=truth_family,
        evidence_digest=arm_digest,
        truth_digest=truth_digest,
        catalogue_configuration_digest=catalogue_configuration_digest,
        radio_configuration_digest=radio_configuration_digest,
        catalogue_fit=catalogue_fit,
        radio_fits=radio_fits,
        audit=audit,
    )


def _fit_and_score(
    training: list[dict[str, Any]],
    future: list[dict[str, Any]],
    *,
    model_kind: Literal["catalogue-orbit", "radio-polynomial"],
    degree: int,
    base_prediction_by_frame: dict[int, float] | None,
    variance_floor_hz2: float,
) -> ModelFitReceipt:
    training_time = _values(training, "reference_time_s")
    future_time = _values(future, "reference_time_s")
    training_y = _values(training, "measured_cfo_hz")
    future_y = _values(future, "measured_cfo_hz")
    training_sigma = _positive_values(training, "standard_uncertainty_hz")
    future_sigma = _positive_values(future, "standard_uncertainty_hz")
    reference = math.fsum(training_time) / len(training_time)
    training_design: tuple[tuple[float, ...], ...]
    future_design: tuple[tuple[float, ...], ...]
    training_target: tuple[float, ...]
    future_base: tuple[float, ...]
    if model_kind == "catalogue-orbit":
        if degree != 0 or base_prediction_by_frame is None:
            raise CrossFamilyQinScoringInputError("catalogue fit needs a fixed curve and offset")
        training_base = tuple(
            base_prediction_by_frame[int(item["frame_index"])] for item in training
        )
        future_base = tuple(base_prediction_by_frame[int(item["frame_index"])] for item in future)
        training_design = tuple((1.0,) for _ in training)
        future_design = tuple((1.0,) for _ in future)
        training_target = tuple(
            observed - base for observed, base in zip(training_y, training_base, strict=True)
        )
    else:
        if degree not in (1, 2, 3) or base_prediction_by_frame is not None:
            raise CrossFamilyQinScoringInputError("radio fit needs a frozen polynomial degree")
        training_design = tuple(_polynomial_row(time - reference, degree) for time in training_time)
        future_design = tuple(_polynomial_row(time - reference, degree) for time in future_time)
        training_target = training_y
        future_base = tuple(0.0 for _ in future)
    training_variance = tuple(sigma * sigma + variance_floor_hz2 for sigma in training_sigma)
    future_variance = tuple(sigma * sigma + variance_floor_hz2 for sigma in future_sigma)
    if min((*training_variance, *future_variance)) <= 0.0:
        raise CrossFamilyQinScoringInputError("predictive variance must be positive")
    parameter_count = degree + 1
    normal = tuple(
        tuple(
            math.fsum(
                row[left] * row[right] / variance
                for row, variance in zip(training_design, training_variance, strict=True)
            )
            for right in range(parameter_count)
        )
        for left in range(parameter_count)
    )
    rhs = tuple(
        math.fsum(
            row[column] * target / variance
            for row, target, variance in zip(
                training_design,
                training_target,
                training_variance,
                strict=True,
            )
        )
        for column in range(parameter_count)
    )
    normal_cholesky = _cholesky(normal, "training normal matrix")
    coefficients = _solve_cholesky(normal_cholesky, rhs)
    coefficient_covariance = _inverse_from_cholesky(normal_cholesky)
    prediction = tuple(
        base
        + math.fsum(
            value * coefficient for value, coefficient in zip(row, coefficients, strict=True)
        )
        for base, row in zip(future_base, future_design, strict=True)
    )
    residual = tuple(
        observed - predicted for observed, predicted in zip(future_y, prediction, strict=True)
    )
    future_information = tuple(
        tuple(
            math.fsum(
                row[left] * row[right] / variance
                for row, variance in zip(future_design, future_variance, strict=True)
            )
            for right in range(parameter_count)
        )
        for left in range(parameter_count)
    )
    predictive_precision = tuple(
        tuple(
            normal[row][column] + future_information[row][column]
            for column in range(parameter_count)
        )
        for row in range(parameter_count)
    )
    predictive_cholesky = _cholesky(
        predictive_precision,
        "predictive information matrix",
    )
    projected_residual = tuple(
        math.fsum(
            row[column] * value / variance
            for row, value, variance in zip(
                future_design,
                residual,
                future_variance,
                strict=True,
            )
        )
        for column in range(parameter_count)
    )
    posterior_shift = _solve_cholesky(predictive_cholesky, projected_residual)
    conditional_residual = tuple(
        value
        - math.fsum(
            coefficient * shift for coefficient, shift in zip(row, posterior_shift, strict=True)
        )
        for row, value in zip(future_design, residual, strict=True)
    )
    mahalanobis = math.fsum(
        value * value / variance
        for value, variance in zip(conditional_residual, future_variance, strict=True)
    ) + _quadratic(normal, posterior_shift)
    if mahalanobis < 0.0 or not math.isfinite(mahalanobis):
        raise CrossFamilyQinScoringNumericalError("predictive quadratic is invalid")
    logdet = math.fsum(math.log(value) for value in future_variance)
    logdet -= _logdet_from_cholesky(normal_cholesky)
    logdet += _logdet_from_cholesky(predictive_cholesky)
    n = len(future)
    nll = 0.5 * math.fsum((mahalanobis, logdet, n * math.log(2.0 * math.pi)))
    rms = math.sqrt(math.fsum(value * value for value in residual) / n)
    summary = _summary(
        model_kind=model_kind,
        model_label="true-causal-tle-tau0-plus-offset" if degree == 0 else f"degree-{degree}",
        observation_count=n,
        residual_rms_hz=rms,
        mahalanobis_squared=mahalanobis,
        log_determinant_covariance=logdet,
        total_nll=nll,
        fitted_parameter_count=degree + 1,
    )
    return ModelFitReceipt(
        model_kind=model_kind,
        degree=degree,
        reference_time_s=reference,
        coefficients_hz=coefficients,
        coefficient_covariance=coefficient_covariance,
        training_observation_count=len(training),
        future_observation_count=n,
        summary=summary,
    )


def _summary(
    *,
    model_kind: Literal["catalogue-orbit", "radio-polynomial"],
    model_label: str,
    observation_count: int,
    residual_rms_hz: float,
    mahalanobis_squared: float,
    log_determinant_covariance: float,
    total_nll: float,
    fitted_parameter_count: int,
) -> PredictiveEvidenceModelSummary:
    values = (residual_rms_hz, mahalanobis_squared, log_determinant_covariance, total_nll)
    if any(not math.isfinite(item) for item in values) or min(values[:2]) < 0.0:
        raise CrossFamilyQinScoringNumericalError("predictive summary is not finite")
    residual_component = 0.5 * mahalanobis_squared
    uncertainty_component = 0.5 * log_determinant_covariance
    normalization_component = 0.5 * observation_count * math.log(2.0 * math.pi)
    reconstructed = math.fsum((residual_component, uncertainty_component, normalization_component))
    tolerance = max(1e-9, 32.0 * math.ulp(max(1.0, abs(reconstructed), abs(total_nll))))
    if abs(reconstructed - total_nll) > tolerance:
        raise CrossFamilyQinScoringNumericalError("predictive NLL decomposition differs")
    geometric_sigma = math.exp(log_determinant_covariance / (2.0 * observation_count))
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
        fitted_continuous_parameter_count=fitted_parameter_count,
        profiled_discrete_state_count=1,
        training_search_family_size=1,
    )


def _comparison(
    catalogue: PredictiveEvidenceModelSummary,
    radio: PredictiveEvidenceModelSummary,
    *,
    degree: int,
) -> CatalogueRadioPredictiveEvidenceComparison:
    rms_preference = _preference_from_losses(
        catalogue.future_residual_rms_hz,
        radio.future_residual_rms_hz,
    )
    nll_preference = _preference_from_losses(
        catalogue.total_predictive_negative_log_likelihood,
        radio.total_predictive_negative_log_likelihood,
    )
    return CatalogueRadioPredictiveEvidenceComparison(
        polynomial_degree=degree,
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


def _calibration_case(
    case: PairedQinCaseScore,
    model_kind: Literal["catalogue-orbit", "radio-polynomial"],
    primary_degree: int,
) -> PredictiveCalibrationCase:
    if model_kind == "catalogue-orbit":
        score = case.catalogue_fit.summary
        configuration = case.catalogue_configuration_digest
    else:
        score = next(item.summary for item in case.radio_fits if item.degree == primary_degree)
        configuration = case.radio_configuration_digest
    return PredictiveCalibrationCase(
        case_id=case.case_id,
        scenario_id=case.scenario_id,
        evidence_digest=case.evidence_digest,
        truth_digest=case.truth_digest,
        model_configuration_digest=configuration,
        score=score,
    )


def _leave_one_out_diagnostic(
    case: PairedQinCaseScore,
    *,
    primary_degree: int,
    catalogue_scale: float,
    radio_scale: float,
) -> LeaveOnePairOutCaseDiagnostic:
    catalogue = case.catalogue_fit.summary
    radio = next(item.summary for item in case.radio_fits if item.degree == primary_degree)
    catalogue_nll = _scaled_nll(catalogue, catalogue_scale)
    radio_nll = _scaled_nll(radio, radio_scale)
    delta = radio_nll - catalogue_nll
    preference = _preference_from_delta(delta)
    return LeaveOnePairOutCaseDiagnostic(
        case_id=case.case_id,
        scenario_id=case.scenario_id,
        truth_model_family=case.truth_model_family,
        observation_count=catalogue.observation_count,
        catalogue_variance_scale_from_other_pairs=catalogue_scale,
        radio_variance_scale_from_other_pairs=radio_scale,
        catalogue_scaled_predictive_negative_log_likelihood=catalogue_nll,
        radio_scaled_predictive_negative_log_likelihood=radio_nll,
        radio_minus_catalogue_scaled_predictive_negative_log_likelihood=delta,
        preference=preference,
        preference_matches_truth=preference == case.truth_model_family,
    )


def _scaled_nll(score: PredictiveEvidenceModelSummary, variance_scale: float) -> float:
    if not math.isfinite(variance_scale) or variance_scale <= 0.0:
        raise CrossFamilyQinScoringNumericalError("leave-one-out scale is not positive")
    value = 0.5 * math.fsum(
        (
            score.mahalanobis_squared / variance_scale,
            score.log_determinant_covariance,
            score.observation_count * math.log(variance_scale),
            score.observation_count * math.log(2.0 * math.pi),
        )
    )
    if not math.isfinite(value):
        raise CrossFamilyQinScoringNumericalError("scaled predictive NLL is not finite")
    return value


def _validate_evidence_envelope(
    evidence: dict[str, Any],
    protocol: dict[str, Any],
    config: CrossFamilyQinScoringConfig,
) -> None:
    if evidence.get("schema") != _EVIDENCE_SCHEMA:
        raise CrossFamilyQinScoringInputError("paired Qin evidence schema differs")
    if evidence.get("protocol_sha256") != config.protocol_sha256:
        raise CrossFamilyQinScoringInputError("paired evidence names another protocol")
    if evidence.get("independent_background_count") != config.independent_background_pair_count:
        raise CrossFamilyQinScoringInputError("paired background count differs")
    if evidence.get("truth_arm_count") != config.truth_arm_count:
        raise CrossFamilyQinScoringInputError("paired truth arm count differs")
    pairs = evidence.get("paired_evidence")
    protocol_pairs = protocol.get("pairs")
    truth_receipts = evidence.get("truth_receipts")
    if not isinstance(pairs, list) or len(pairs) != config.independent_background_pair_count:
        raise CrossFamilyQinScoringInputError("paired evidence inventory differs")
    if not isinstance(protocol_pairs, list) or not isinstance(truth_receipts, list):
        raise CrossFamilyQinScoringInputError("paired protocol or truth receipts are absent")
    signal = protocol.get("signal_and_measurement")
    scoring = protocol.get("scoring")
    if not isinstance(signal, dict) or not isinstance(scoring, dict):
        raise CrossFamilyQinScoringInputError("paired protocol scoring inventory is absent")
    frame_count = signal.get("frame_count")
    training_fraction = scoring.get("training_fraction")
    if not isinstance(frame_count, int) or frame_count < 1 or training_fraction != 0.6:
        raise CrossFamilyQinScoringInputError("paired protocol frame partition differs")
    training_count = round(frame_count * float(training_fraction))
    if training_count <= 0 or training_count >= frame_count:
        raise CrossFamilyQinScoringInputError("paired protocol frame partition is empty")
    for pair in pairs:
        for lane in ("orbit", "radio"):
            arm = pair.get(lane)
            rows = arm.get("observation_rows") if isinstance(arm, dict) else None
            if not isinstance(rows, list) or len(rows) != frame_count:
                raise CrossFamilyQinScoringInputError("paired arm frame count differs")
            if tuple(item.get("frame_index") for item in rows) != tuple(range(frame_count)):
                raise CrossFamilyQinScoringInputError("paired arm frame sequence differs")
            if any(item.get("split") != "training-even-qin" for item in rows[:training_count]) or (
                any(item.get("split") != "future-odd-qin" for item in rows[training_count:])
            ):
                raise CrossFamilyQinScoringInputError("paired arm frame split differs")
            if (
                arm.get("training_opportunity_count") != training_count
                or arm.get("future_opportunity_count") != frame_count - training_count
            ):
                raise CrossFamilyQinScoringInputError("paired arm opportunity counts differ")
    pair_ids = tuple(_required_string(item, "pair_id") for item in pairs)
    if len(set(pair_ids)) != len(pair_ids):
        raise CrossFamilyQinScoringInputError("paired evidence identities repeat")
    if set(pair_ids) != {_required_string(item, "pair_id") for item in protocol_pairs}:
        raise CrossFamilyQinScoringInputError("paired evidence and protocol inventories differ")
    if set(pair_ids) != {_required_string(item, "pair_id") for item in truth_receipts}:
        raise CrossFamilyQinScoringInputError("paired evidence and truth inventories differ")
    claim = evidence.get("claim_boundary")
    if not isinstance(claim, dict) or any(
        claim.get(key) is not False
        for key in (
            "formal_coverage_claimed",
            "threshold_fitted",
            "posterior_odds_produced",
            "identity_claimed",
            "positioning_validated",
        )
    ):
        raise CrossFamilyQinScoringInputError("paired evidence claim boundary differs")


def _validate_pair_identity(
    pair: dict[str, Any],
    protocol_pair: dict[str, Any],
    truth: dict[str, Any],
) -> None:
    pair_id = _required_string(pair, "pair_id")
    if (
        pair.get("background_session_id") != protocol_pair.get("background_session_id")
        or pair.get("occupancy_identical") is not True
        or pair.get("identity_claimed") is not False
        or pair.get("threshold_fitted") is not False
        or truth.get("catalog_number") != protocol_pair.get("true_catalog_number")
        or truth.get("object_name") != protocol_pair.get("true_object_name")
    ):
        raise CrossFamilyQinScoringInputError(f"paired identity authority differs: {pair_id}")
    orbit = pair.get("orbit")
    radio = pair.get("radio")
    if not isinstance(orbit, dict) or not isinstance(radio, dict):
        raise CrossFamilyQinScoringInputError("paired truth arms are absent")
    if orbit.get("truth_family") != "catalogue-orbit" or radio.get("truth_family") != (
        "radio-polynomial"
    ):
        raise CrossFamilyQinScoringInputError("paired truth family labels differ")
    if any(
        arm.get("future_response_used_for_training") is not False
        or arm.get("training_uses_even_qin_only") is not True
        or arm.get("future_uses_odd_qin_only") is not True
        for arm in (orbit, radio)
    ):
        raise CrossFamilyQinScoringInputError("paired response partition differs")


def _revalidate_config(value: CrossFamilyQinScoringConfig) -> CrossFamilyQinScoringConfig:
    try:
        copied = CrossFamilyQinScoringConfig(
            evidence_path=value.evidence_path,
            evidence_sha256=value.evidence_sha256,
            protocol_path=value.protocol_path,
            protocol_sha256=value.protocol_sha256,
            independent_background_pair_count=value.independent_background_pair_count,
            truth_arm_count=value.truth_arm_count,
            primary_degree=value.primary_degree,
            diagnostic_degrees=cast(tuple[Literal[2], Literal[3]], tuple(value.diagnostic_degrees)),
            additional_variance_floor_hz2=value.additional_variance_floor_hz2,
            minimum_independent_pairs=value.minimum_independent_pairs,
            formal_95_percent_rank_minimum_pairs=value.formal_95_percent_rank_minimum_pairs,
            result_path=value.result_path,
            report_path=value.report_path,
            config_digest=value.config_digest,
        )
    except (AttributeError, TypeError, ValueError) as error:
        raise CrossFamilyQinScoringInputError("predictive scoring config is invalid") from error
    if (
        copied.primary_degree != 1
        or copied.diagnostic_degrees != (2, 3)
        or copied.independent_background_pair_count < copied.minimum_independent_pairs
        or copied.truth_arm_count != 2 * copied.independent_background_pair_count
        or copied.formal_95_percent_rank_minimum_pairs < 19
        or not math.isfinite(copied.additional_variance_floor_hz2)
        or copied.additional_variance_floor_hz2 < 0.0
        or not _is_digest(copied.evidence_sha256)
        or not _is_digest(copied.protocol_sha256)
        or not _is_digest(copied.config_digest)
    ):
        raise CrossFamilyQinScoringInputError("predictive scoring config semantics are invalid")
    return copied


def _values(rows: list[dict[str, Any]], key: str) -> tuple[float, ...]:
    return tuple(_finite_float(item.get(key), key) for item in rows)


def _positive_values(rows: list[dict[str, Any]], key: str) -> tuple[float, ...]:
    values = _values(rows, key)
    if min(values) <= 0.0:
        raise CrossFamilyQinScoringInputError(f"{key} must be positive")
    return values


def _polynomial_row(offset_s: float, degree: int) -> tuple[float, ...]:
    return tuple(offset_s**power for power in range(degree + 1))


def _cholesky(
    matrix: tuple[tuple[float, ...], ...],
    label: str,
) -> tuple[tuple[float, ...], ...]:
    size = len(matrix)
    if size < 1 or any(len(row) != size for row in matrix):
        raise CrossFamilyQinScoringNumericalError(f"{label} is not square")
    lower = [[0.0 for _ in range(size)] for _ in range(size)]
    for row in range(size):
        for column in range(row + 1):
            remainder = matrix[row][column] - math.fsum(
                lower[row][index] * lower[column][index] for index in range(column)
            )
            if row == column:
                if not math.isfinite(remainder) or remainder <= 0.0:
                    raise CrossFamilyQinScoringNumericalError(f"{label} is not SPD")
                lower[row][column] = math.sqrt(remainder)
            else:
                value = remainder / lower[column][column]
                if not math.isfinite(value):
                    raise CrossFamilyQinScoringNumericalError(f"{label} is not finite")
                lower[row][column] = value
    return tuple(tuple(item for item in row) for row in lower)


def _solve_cholesky(
    lower: tuple[tuple[float, ...], ...],
    right_hand_side: tuple[float, ...],
) -> tuple[float, ...]:
    size = len(lower)
    if len(right_hand_side) != size:
        raise CrossFamilyQinScoringNumericalError("linear solve dimensions differ")
    forward: list[float] = []
    for row in range(size):
        value = (
            right_hand_side[row]
            - math.fsum(lower[row][column] * forward[column] for column in range(row))
        ) / lower[row][row]
        if not math.isfinite(value):
            raise CrossFamilyQinScoringNumericalError("forward solve is not finite")
        forward.append(value)
    result = [0.0 for _ in range(size)]
    for row in range(size - 1, -1, -1):
        value = (
            forward[row]
            - math.fsum(lower[column][row] * result[column] for column in range(row + 1, size))
        ) / lower[row][row]
        if not math.isfinite(value):
            raise CrossFamilyQinScoringNumericalError("back solve is not finite")
        result[row] = value
    return tuple(result)


def _inverse_from_cholesky(
    lower: tuple[tuple[float, ...], ...],
) -> tuple[tuple[float, ...], ...]:
    size = len(lower)
    columns = tuple(
        _solve_cholesky(
            lower,
            tuple(1.0 if row == column else 0.0 for row in range(size)),
        )
        for column in range(size)
    )
    return tuple(
        tuple(0.5 * (columns[column][row] + columns[row][column]) for column in range(size))
        for row in range(size)
    )


def _quadratic(
    matrix: tuple[tuple[float, ...], ...],
    vector: tuple[float, ...],
) -> float:
    return math.fsum(
        vector[row]
        * math.fsum(matrix[row][column] * vector[column] for column in range(len(vector)))
        for row in range(len(vector))
    )


def _logdet_from_cholesky(lower: tuple[tuple[float, ...], ...]) -> float:
    value = 2.0 * math.fsum(math.log(lower[index][index]) for index in range(len(lower)))
    if not math.isfinite(value):
        raise CrossFamilyQinScoringNumericalError("matrix log determinant is not finite")
    return value


def _observation_id(arm_digest: str, row: dict[str, Any]) -> str:
    return canonical_digest(
        {
            "arm_evidence_digest": arm_digest,
            "frame_index": row.get("frame_index"),
            "split": row.get("split"),
            "reference_time_s": row.get("reference_time_s"),
            "absolute_frame_start_sample": row.get("absolute_frame_start_sample"),
        }
    )


def _nis_direction(value: float) -> NisDirection:
    tolerance = 8.0 * math.ulp(max(1.0, abs(value)))
    if abs(value - 1.0) <= tolerance:
        return "equal-one-within-float"
    return "below-one" if value < 1.0 else "above-one"


def _preference_from_losses(catalogue: float, radio: float) -> ScorePreference:
    return _preference_from_delta(radio - catalogue)


def _preference_from_delta(delta: float) -> ModelPreference:
    if not math.isfinite(delta):
        raise CrossFamilyQinScoringNumericalError("model preference is not finite")
    tolerance = 8.0 * math.ulp(max(1.0, abs(delta)))
    if abs(delta) <= tolerance:
        return "exact-tie"
    return "catalogue-orbit" if delta > 0.0 else "radio-polynomial"


def _finite_float(value: object, label: str) -> float:
    if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise CrossFamilyQinScoringInputError(f"{label} is not finite")
    return float(value)


def _required_string(value: dict[str, Any], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item:
        raise CrossFamilyQinScoringInputError(f"{key} is missing")
    return item


def _required_digest(value: dict[str, Any], key: str) -> str:
    item = _required_string(value, key)
    if not _is_digest(item):
        raise CrossFamilyQinScoringInputError(f"{key} is not a digest")
    return item


def _is_digest(value: str) -> bool:
    return (
        value.startswith("sha256:")
        and len(value) == 71
        and all(character in "0123456789abcdef" for character in value[7:])
    )


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _json_object(value: bytes, label: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as error:
        raise CrossFamilyQinScoringInputError(f"{label} is not JSON") from error
    if not isinstance(parsed, dict):
        raise CrossFamilyQinScoringInputError(f"{label} is not an object")
    return parsed
