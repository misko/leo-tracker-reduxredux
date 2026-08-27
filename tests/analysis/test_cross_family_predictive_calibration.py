from __future__ import annotations

import math
from dataclasses import replace
from typing import Literal

import pytest

from leo.analysis.research.cross_family_predictive_calibration import (
    CrossFamilyCalibrationConfig,
    CrossFamilyCalibrationInputError,
    CrossFamilyKnownTruthCase,
    CrossFamilyPredictiveCalibrationAudit,
    audit_known_truth_cross_family_prediction,
)
from leo.analysis.research.predictive_evidence_diagnostics import (
    CatalogueRadioPredictiveEvidenceAudit,
    PredictiveEvidenceModelSummary,
    audit_catalogue_radio_predictive_evidence,
)
from leo.analysis.research.predictive_uncertainty_calibration import (
    PredictiveCalibrationCase,
    PredictiveCalibrationConfig,
    PredictiveCovarianceScaleCalibration,
    calibrate_uniform_predictive_covariance,
)
from leo.analysis.research.radio_polynomial_null import RadioPolynomialNullResult
from leo.contracts.digests import canonical_digest
from tests.analysis.test_predictive_evidence_diagnostics import (
    _association_and_radio,
    _radio_score,
)

_ATTESTATION: Literal["scenario-groups-frozen-response-free-and-independent-v1"] = (
    "scenario-groups-frozen-response-free-and-independent-v1"
)
_CATALOGUE_CONFIG = canonical_digest({"model": "catalogue-orbit-calibrated"})
_RADIO_CONFIG = canonical_digest({"model": "radio-cubic-calibrated"})


def _unit_nis_summary(kind: str) -> PredictiveEvidenceModelSummary:
    observation_count = 4
    variance = 4.0
    mahalanobis = float(observation_count)
    logdet = observation_count * math.log(variance)
    nll = 0.5 * (mahalanobis + logdet + observation_count * math.log(2.0 * math.pi))
    return PredictiveEvidenceModelSummary(
        model_kind=kind,  # type: ignore[arg-type]
        model_label=f"{kind}-calibration",
        observation_count=observation_count,
        future_residual_rms_hz=2.0,
        mahalanobis_squared=mahalanobis,
        mean_normalized_innovation_squared=1.0,
        nis_direction="equal-one-within-float",
        log_determinant_covariance=logdet,
        geometric_mean_predictive_standard_uncertainty_hz=2.0,
        residual_fit_negative_log_likelihood_component=0.5 * mahalanobis,
        uncertainty_volume_negative_log_likelihood_component=0.5 * logdet,
        gaussian_normalization_negative_log_likelihood_component=(
            0.5 * observation_count * math.log(2.0 * math.pi)
        ),
        total_predictive_negative_log_likelihood=nll,
        predictive_negative_log_likelihood_per_observation=nll / observation_count,
        fitted_continuous_parameter_count=1,
        profiled_discrete_state_count=1,
        training_search_family_size=1,
    )


def _covariance_calibration(
    kind: str, configuration_digest: str
) -> PredictiveCovarianceScaleCalibration:
    cases = tuple(
        PredictiveCalibrationCase(
            case_id=f"scale-{kind}-{index}",
            scenario_id=f"scale-scenario-{kind}-{index}",
            evidence_digest=canonical_digest({"scale-evidence": (kind, index)}),
            truth_digest=canonical_digest({"scale-truth": (kind, index)}),
            model_configuration_digest=configuration_digest,
            score=_unit_nis_summary(kind),
        )
        for index in range(3)
    )
    return calibrate_uniform_predictive_covariance(
        cases,
        PredictiveCalibrationConfig(
            model_kind=kind,  # type: ignore[arg-type]
            model_configuration_digest=configuration_digest,
            expected_case_ids=tuple(item.case_id for item in cases),
            independence_attestation=_ATTESTATION,
        ),
    )


def _audit(*, truth: str) -> CatalogueRadioPredictiveEvidenceAudit:
    association, radio = _association_and_radio()
    if truth == "catalogue-orbit":
        radio = RadioPolynomialNullResult(
            graph_content_digest=radio.graph_content_digest,
            observation_partition_digest=radio.observation_partition_digest,
            training_observation_ids=radio.training_observation_ids,
            evaluation_observation_ids=radio.evaluation_observation_ids,
            scores=tuple(_radio_score(degree=degree, residual_rms_hz=10.0) for degree in (1, 2, 3)),
        )
    return audit_catalogue_radio_predictive_evidence(
        association,
        radio,
        catalogue_training_rank=1,
    )


def _cases() -> tuple[CrossFamilyKnownTruthCase, ...]:
    result = []
    for truth, prefix in (
        ("catalogue-orbit", "orbit"),
        ("radio-polynomial", "radio"),
    ):
        for index in range(3):
            result.append(
                CrossFamilyKnownTruthCase(
                    case_id=f"paired-{prefix}-{index}",
                    scenario_id=f"scenario-{prefix}-{index}",
                    evidence_digest=canonical_digest({"paired-evidence": (prefix, index)}),
                    truth_digest=canonical_digest({"paired-truth": (prefix, index)}),
                    truth_model_family=truth,  # type: ignore[arg-type]
                    catalogue_model_configuration_digest=_CATALOGUE_CONFIG,
                    radio_model_configuration_digest=_RADIO_CONFIG,
                    audit=_audit(truth=truth),
                )
            )
    return tuple(result)


def _config(cases: tuple[CrossFamilyKnownTruthCase, ...]) -> CrossFamilyCalibrationConfig:
    return CrossFamilyCalibrationConfig(
        expected_case_ids=tuple(item.case_id for item in cases),
        polynomial_degree=3,
        catalogue_model_configuration_digest=_CATALOGUE_CONFIG,
        radio_model_configuration_digest=_RADIO_CONFIG,
        independence_attestation=_ATTESTATION,
    )


def _run(
    cases: tuple[CrossFamilyKnownTruthCase, ...] | None = None,
) -> CrossFamilyPredictiveCalibrationAudit:
    cases = _cases() if cases is None else cases
    return audit_known_truth_cross_family_prediction(
        cases,
        _config(cases),
        catalogue_covariance_calibration=_covariance_calibration(
            "catalogue-orbit", _CATALOGUE_CONFIG
        ),
        radio_covariance_calibration=_covariance_calibration("radio-polynomial", _RADIO_CONFIG),
    )


def test_known_truth_families_are_compared_after_independent_scaling() -> None:
    audit = _run()

    assert audit.catalogue_truth_scenario_count == 3
    assert audit.radio_truth_scenario_count == 3
    assert audit.correct_scenario_count == 6
    assert audit.tied_scenario_count == 0
    assert audit.scenario_equal_accuracy == 1.0
    assert all(item.catalogue.variance_scale == 1.0 for item in audit.case_scores)
    assert all(item.radio.variance_scale == 1.0 for item in audit.case_scores)
    assert audit.threshold_fitted is False
    assert audit.formal_coverage_claimed is False
    assert audit.posterior_odds_produced is False
    assert audit.model_selection_gate_produced is False
    assert audit.identity_claimed is False
    assert audit.formal_95_percent_rank_scenario_count_sufficient is False


def test_cases_are_averaged_within_scenario_before_accuracy() -> None:
    cases = _cases()
    duplicate = replace(
        cases[0],
        case_id="paired-orbit-duplicate",
        evidence_digest=canonical_digest({"paired-evidence": "duplicate"}),
    )
    expanded = (cases[0], duplicate, *cases[1:])

    audit = _run(expanded)

    assert len(audit.case_scores) == 7
    assert len(audit.scenario_diagnostics) == 6
    assert audit.scenario_diagnostics[0].case_count == 2
    assert audit.scenario_equal_accuracy == 1.0


def test_too_few_scenarios_in_one_truth_family_is_refused() -> None:
    cases = tuple(item for item in _cases() if item.scenario_id != "scenario-radio-2")

    with pytest.raises(CrossFamilyCalibrationInputError, match="too few"):
        _run(cases)


def test_truth_authority_cannot_change_within_one_scenario() -> None:
    cases = _cases()
    conflicting = replace(
        cases[0],
        case_id="paired-orbit-conflict",
        evidence_digest=canonical_digest({"paired-evidence": "conflict"}),
        truth_digest=canonical_digest({"paired-truth": "different"}),
    )

    with pytest.raises(CrossFamilyCalibrationInputError, match="mixes truth"):
        _run((cases[0], conflicting, *cases[1:]))


def test_covariance_calibration_evidence_cannot_reappear_as_target() -> None:
    cases = _cases()
    calibration = _covariance_calibration("catalogue-orbit", _CATALOGUE_CONFIG)
    poisoned = replace(cases[0], evidence_digest=calibration.calibration_evidence_digests[0])
    changed = (poisoned, *cases[1:])

    with pytest.raises(CrossFamilyCalibrationInputError, match="not disjoint"):
        audit_known_truth_cross_family_prediction(
            changed,
            _config(changed),
            catalogue_covariance_calibration=calibration,
            radio_covariance_calibration=_covariance_calibration("radio-polynomial", _RADIO_CONFIG),
        )


def test_stale_nested_score_decomposition_is_rejected() -> None:
    cases = _cases()
    audit = cases[0].audit
    comparison = audit.comparisons[2]
    poisoned_catalogue = replace(
        comparison.catalogue,
        total_predictive_negative_log_likelihood=(
            comparison.catalogue.total_predictive_negative_log_likelihood + 1.0
        ),
    )
    poisoned_comparison = replace(comparison, catalogue=poisoned_catalogue)
    poisoned_audit = replace(
        audit,
        comparisons=(*audit.comparisons[:2], poisoned_comparison),
    )
    changed = (replace(cases[0], audit=poisoned_audit), *cases[1:])

    with pytest.raises(CrossFamilyCalibrationInputError, match="decomposition"):
        _run(changed)
