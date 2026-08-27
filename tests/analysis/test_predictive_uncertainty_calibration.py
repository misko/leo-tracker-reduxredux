from __future__ import annotations

import math
from dataclasses import replace
from typing import Literal

import pytest

from leo.analysis.research.predictive_evidence_diagnostics import (
    PredictiveEvidenceModelSummary,
)
from leo.analysis.research.predictive_uncertainty_calibration import (
    PredictiveCalibrationCase,
    PredictiveCalibrationConfig,
    PredictiveCalibrationInputError,
    PredictiveCalibrationNumericalError,
    apply_uniform_predictive_covariance_scale,
    calibrate_uniform_predictive_covariance,
)
from leo.contracts.digests import canonical_digest

_CONFIG_DIGEST = canonical_digest({"model": "catalogue-orbit-synthetic-v1"})
_ATTESTATION: Literal["scenario-groups-frozen-response-free-and-independent-v1"] = (
    "scenario-groups-frozen-response-free-and-independent-v1"
)


def _score(*, observation_count: int, mean_nis: float) -> PredictiveEvidenceModelSummary:
    mahalanobis = observation_count * mean_nis
    log_determinant = 0.0
    residual_component = 0.5 * mahalanobis
    uncertainty_component = 0.0
    normalization_component = 0.5 * observation_count * math.log(2.0 * math.pi)
    total_nll = residual_component + uncertainty_component + normalization_component
    direction: Literal["below-one", "equal-one-within-float", "above-one"] = (
        "equal-one-within-float"
        if mean_nis == 1.0
        else "below-one"
        if mean_nis < 1.0
        else "above-one"
    )
    return PredictiveEvidenceModelSummary(
        model_kind="catalogue-orbit",
        model_label="synthetic-orbit",
        observation_count=observation_count,
        future_residual_rms_hz=math.sqrt(mean_nis),
        mahalanobis_squared=mahalanobis,
        mean_normalized_innovation_squared=mean_nis,
        nis_direction=direction,
        log_determinant_covariance=log_determinant,
        geometric_mean_predictive_standard_uncertainty_hz=1.0,
        residual_fit_negative_log_likelihood_component=residual_component,
        uncertainty_volume_negative_log_likelihood_component=uncertainty_component,
        gaussian_normalization_negative_log_likelihood_component=normalization_component,
        total_predictive_negative_log_likelihood=total_nll,
        predictive_negative_log_likelihood_per_observation=total_nll / observation_count,
        fitted_continuous_parameter_count=1,
        profiled_discrete_state_count=1,
        training_search_family_size=10,
    )


def _case(
    case_id: str,
    scenario_id: str,
    *,
    observation_count: int,
    mean_nis: float,
) -> PredictiveCalibrationCase:
    return PredictiveCalibrationCase(
        case_id=case_id,
        scenario_id=scenario_id,
        evidence_digest=canonical_digest({"evidence": case_id}),
        truth_digest=canonical_digest({"truth": case_id}),
        model_configuration_digest=_CONFIG_DIGEST,
        score=_score(observation_count=observation_count, mean_nis=mean_nis),
    )


def _cases() -> tuple[PredictiveCalibrationCase, ...]:
    return (
        _case("a-1", "scenario-a", observation_count=100, mean_nis=4.0),
        _case("a-2", "scenario-a", observation_count=10, mean_nis=2.0),
        _case("b-1", "scenario-b", observation_count=1, mean_nis=1.0),
        _case("c-1", "scenario-c", observation_count=1, mean_nis=2.0),
    )


def _config(cases: tuple[PredictiveCalibrationCase, ...]) -> PredictiveCalibrationConfig:
    return PredictiveCalibrationConfig(
        model_kind="catalogue-orbit",
        model_configuration_digest=_CONFIG_DIGEST,
        expected_case_ids=tuple(item.case_id for item in cases),
        independence_attestation=_ATTESTATION,
    )


def test_scale_is_scenario_equal_not_row_or_case_pooled() -> None:
    cases = _cases()

    calibration = calibrate_uniform_predictive_covariance(cases, _config(cases))

    assert calibration.scenario_equal_variance_scale == pytest.approx(2.0)
    assert calibration.scenario_equal_standard_deviation_scale == pytest.approx(math.sqrt(2.0))
    assert calibration.observation_pooled_variance_scale == pytest.approx(423.0 / 112.0)
    assert calibration.case_count == 4
    assert calibration.scenario_count == 3
    assert calibration.observation_count == 112
    scenario_a = calibration.scenario_diagnostics[0]
    assert scenario_a.scenario_id == "scenario-a"
    assert scenario_a.raw_scenario_mean_normalized_innovation_squared == pytest.approx(3.0)
    assert scenario_a.leave_one_scenario_out_variance_scale == pytest.approx(1.5)
    assert (
        scenario_a.leave_one_scenario_out_calibrated_mean_normalized_innovation_squared
        == pytest.approx(2.0)
    )
    assert calibration.formal_95_percent_rank_coverage_scenario_count_sufficient is False
    assert calibration.formal_coverage_claimed is False
    assert calibration.covariance_shape_changed is False
    assert calibration.covariance_shape_calibrated is False
    assert calibration.posterior_probability_produced is False
    assert calibration.model_selection_gate_produced is False


def test_prelearned_scale_applies_to_an_excluded_target() -> None:
    cases = _cases()
    calibration = calibrate_uniform_predictive_covariance(cases, _config(cases))
    target = _score(observation_count=20, mean_nis=3.0)

    applied = apply_uniform_predictive_covariance_scale(
        target,
        calibration,
        target_group_id="sealed-target",
        target_evidence_digest=canonical_digest({"evidence": "sealed-target"}),
        model_configuration_digest=_CONFIG_DIGEST,
    )

    assert applied.variance_scale == pytest.approx(2.0)
    assert applied.scaled_mean_normalized_innovation_squared == pytest.approx(1.5)
    assert applied.scaled_log_determinant_covariance == pytest.approx(20.0 * math.log(2.0))
    expected_nll = 0.5 * (60.0 / 2.0 + 20.0 * math.log(2.0) + 20.0 * math.log(2.0 * math.pi))
    assert applied.scaled_predictive_negative_log_likelihood == pytest.approx(expected_nll)
    assert applied.target_excluded_from_calibration_cases is True
    assert applied.covariance_shape_changed is False
    assert applied.posterior_probability_produced is False


def test_target_cannot_be_one_of_the_calibration_cases() -> None:
    cases = _cases()
    calibration = calibrate_uniform_predictive_covariance(cases, _config(cases))

    with pytest.raises(PredictiveCalibrationInputError, match="used during calibration"):
        apply_uniform_predictive_covariance_scale(
            _score(observation_count=5, mean_nis=1.0),
            calibration,
            target_group_id="a-1",
            target_evidence_digest=canonical_digest({"evidence": "new-target"}),
            model_configuration_digest=_CONFIG_DIGEST,
        )


def test_rewrapped_calibration_evidence_cannot_be_used_as_a_target() -> None:
    cases = _cases()
    calibration = calibrate_uniform_predictive_covariance(cases, _config(cases))

    with pytest.raises(PredictiveCalibrationInputError, match="used during calibration"):
        apply_uniform_predictive_covariance_scale(
            _score(observation_count=5, mean_nis=1.0),
            calibration,
            target_group_id="renamed-target",
            target_evidence_digest=cases[0].evidence_digest,
            model_configuration_digest=_CONFIG_DIGEST,
        )


def test_stale_calibration_result_is_revalidated_before_application() -> None:
    cases = _cases()
    calibration = calibrate_uniform_predictive_covariance(cases, _config(cases))
    poisoned = replace(calibration, scenario_equal_variance_scale=3.0)

    with pytest.raises(PredictiveCalibrationInputError, match="variance and deviation"):
        apply_uniform_predictive_covariance_scale(
            _score(observation_count=5, mean_nis=1.0),
            poisoned,
            target_group_id="sealed-target",
            target_evidence_digest=canonical_digest({"evidence": "sealed-target"}),
            model_configuration_digest=_CONFIG_DIGEST,
        )


def test_case_inventory_and_independent_scenario_floor_are_fail_closed() -> None:
    cases = _cases()
    missing = cases[:-1]

    with pytest.raises(PredictiveCalibrationInputError, match="inventory differs"):
        calibrate_uniform_predictive_covariance(missing, _config(cases))

    two_scenarios = cases[:3]
    with pytest.raises(PredictiveCalibrationInputError, match="too few independent scenarios"):
        calibrate_uniform_predictive_covariance(two_scenarios, _config(two_scenarios))


def test_inconsistent_or_stale_score_summary_is_rejected() -> None:
    cases = _cases()
    poisoned_score = replace(cases[0].score, mean_normalized_innovation_squared=0.1)
    poisoned = (replace(cases[0], score=poisoned_score), *cases[1:])

    with pytest.raises(PredictiveCalibrationInputError, match="decomposition is inconsistent"):
        calibrate_uniform_predictive_covariance(poisoned, _config(cases))


def test_zero_information_scale_is_not_silently_floored() -> None:
    cases = tuple(
        _case(f"zero-{index}", f"scenario-{index}", observation_count=5, mean_nis=0.0)
        for index in range(3)
    )

    with pytest.raises(PredictiveCalibrationNumericalError, match="finite and positive"):
        calibrate_uniform_predictive_covariance(cases, _config(cases))


def test_extreme_finite_scenario_scores_fail_closed_before_overflow() -> None:
    cases = tuple(
        _case(f"huge-{index}", f"scenario-{index}", observation_count=1, mean_nis=1e308)
        for index in range(3)
    )

    with pytest.raises(PredictiveCalibrationNumericalError, match="not representable"):
        calibrate_uniform_predictive_covariance(cases, _config(cases))


def test_nineteen_scenarios_only_marks_rank_count_sufficient() -> None:
    cases = tuple(
        _case(f"case-{index}", f"scenario-{index}", observation_count=5, mean_nis=1.0)
        for index in range(19)
    )

    calibration = calibrate_uniform_predictive_covariance(cases, _config(cases))

    assert calibration.formal_95_percent_rank_coverage_scenario_count_sufficient is True
    assert calibration.formal_coverage_claimed is False
